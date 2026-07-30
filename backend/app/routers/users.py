from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user, get_current_user_with_categories
from app.config import settings
from app.database import get_db
from app.game import PULSE_MARKET_KIND, simulate_crowd
from app.models import (
    BalanceTransaction,
    Category,
    Market,
    Prediction,
    User,
)
from app.schemas import (
    ActivityDayOut,
    AppBootstrapOut,
    CategoryOut,
    DistributionPointOut,
    HistoryPredictionOut,
    MarketOptionOut,
    ProfileStatsOut,
    SetCategoriesIn,
    UserOut,
    WalletOut,
    WalletTransactionOut,
)
from app.routers.leaderboard import build_leaderboard

router = APIRouter(tags=["users"])


def _wallet_totals(predictions: list[Prediction]) -> tuple[int, int, int]:
    total_stakes = sum(prediction.stake_cents or 0 for prediction in predictions)
    settled_predictions = [
        prediction for prediction in predictions if prediction.settled_at is not None
    ]
    total_payouts = sum(
        prediction.payout_cents or 0 for prediction in settled_predictions
    )
    settled_stakes = sum(
        prediction.stake_cents or 0 for prediction in settled_predictions
    )
    return total_stakes, total_payouts, total_payouts - settled_stakes


def _wallet_out(
    user: User,
    totals: tuple[int, int, int],
    transaction_rows: list,
) -> WalletOut:
    total_stakes, total_payouts, net_pnl = totals
    return WalletOut(
        available_balance_cents=user.balance_cents,
        total_stakes_cents=total_stakes,
        total_payouts_cents=total_payouts,
        net_pnl_cents=net_pnl,
        debug_topup_enabled=settings.debug,
        transactions=[
            WalletTransactionOut(
                id=transaction.id,
                transaction_type=transaction.transaction_type,
                amount_cents=transaction.amount_cents,
                balance_after_cents=transaction.balance_after_cents,
                prediction_id=transaction.prediction_id,
                question=question or prompt,
                created_at=transaction.created_at,
            )
            for transaction, question, prompt in transaction_rows
        ],
    )


def _category_out(category: Category) -> CategoryOut:
    return CategoryOut.model_validate(category)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        balance_cents=user.balance_cents,
        pulse_score=user.pulse_score,
        categories=[_category_out(category) for category in user.categories if category.is_active],
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user_with_categories)):
    return _user_out(user)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
    )
    return result.scalars().all()


@router.post("/me/categories", response_model=UserOut)
async def set_categories(
    payload: SetCategoriesIn,
    user: User = Depends(get_current_user_with_categories),
    db: AsyncSession = Depends(get_db),
):
    unique_ids = set(payload.category_ids)
    result = await db.execute(
        select(Category).where(
            Category.id.in_(unique_ids),
            Category.is_active.is_(True),
        )
    )
    categories = list(result.scalars().all())
    if len(categories) != len(unique_ids):
        raise HTTPException(400, "One or more categories are not active Pulse categories")
    user.categories = categories
    await db.commit()
    await db.refresh(user)
    return _user_out(user)


@router.get("/me/history", response_model=list[HistoryPredictionOut])
async def history(
    limit: int = Query(100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Prediction, Market, Category)
            .join(Market, Market.id == Prediction.market_id)
            .join(Category, Category.id == Market.category_id)
            .where(
                Prediction.user_id == user.id,
                Market.market_kind == PULSE_MARKET_KIND,
            )
            .order_by(Prediction.locked_at.desc())
            .limit(limit)
            .options(joinedload(Market.options))
        )
    ).unique().all()
    now = datetime.now(timezone.utc)
    output: list[HistoryPredictionOut] = []
    for prediction, market, category in rows:
        options = sorted(market.options, key=lambda option: option.display_order)
        vote = next(option for option in options if option.id == prediction.vote_option_id)
        forecast_map = prediction.forecast_bps or {}
        actual_map = prediction.actual_distribution_bps or {}
        available_at = prediction.locked_at + timedelta(seconds=prediction.reveal_seconds)
        seconds_remaining = max(0, int((available_at - now).total_seconds()))
        status = "revealed" if prediction.revealed_at else "ready" if seconds_remaining == 0 else "active"
        if prediction.total_participants:
            participant_count = prediction.total_participants - 1
            pool_volume = (prediction.gross_pool_cents or 0) - (prediction.stake_cents or 0)
        else:
            crowd = simulate_crowd(
                market.id,
                [option.id for option in options],
                market.simulation_weights_bps or [],
            )
            participant_count = crowd.participant_count
            pool_volume = crowd.pool_volume_cents
        forecast = [
            DistributionPointOut(
                option_id=option.id,
                key=option.option_key,
                label=option.label,
                bps=forecast_map[str(option.id)],
            )
            for option in options
        ]
        actual = None
        if prediction.revealed_at:
            actual = [
                DistributionPointOut(
                    option_id=option.id,
                    key=option.option_key,
                    label=option.label,
                    bps=actual_map[str(option.id)],
                )
                for option in options
            ]
        output.append(
            HistoryPredictionOut(
                id=prediction.id,
                market_id=market.id,
                question=market.question or market.prompt,
                category_name=category.name,
                category_slug=category.slug,
                status=status,
                vote=MarketOptionOut(
                    id=vote.id, key=vote.option_key, label=vote.label, display_order=vote.display_order
                ),
                forecast=forecast,
                actual_distribution=actual,
                locked_at=prediction.locked_at,
                reveal_seconds=prediction.reveal_seconds,
                reveal_at=available_at,
                seconds_remaining=seconds_remaining,
                participant_count=participant_count,
                pool_volume_cents=pool_volume,
                stake_cents=prediction.stake_cents or 0,
                user_fee_cents=prediction.user_fee_cents or 0,
                accuracy_score=prediction.accuracy_score,
                accuracy_percentile=prediction.accuracy_percentile,
                forecast_rank=prediction.forecast_rank,
                total_participants=prediction.total_participants,
                payout_cents=prediction.payout_cents,
                pnl_cents=prediction.pnl_cents,
                pulse_delta=prediction.pulse_delta if prediction.revealed_at else None,
                revealed_at=prediction.revealed_at,
            )
        )
    return output


@router.get("/me/wallet", response_model=WalletOut)
async def wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total_stakes, total_payouts, net_pnl = (
        await db.execute(
            select(
                func.coalesce(func.sum(Prediction.stake_cents), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (Prediction.settled_at.is_not(None), Prediction.payout_cents),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Prediction.settled_at.is_not(None),
                                func.coalesce(Prediction.payout_cents, 0)
                                - func.coalesce(Prediction.stake_cents, 0),
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .join(Market, Market.id == Prediction.market_id)
            .where(
                Prediction.user_id == user.id,
                Market.market_kind == PULSE_MARKET_KIND,
            )
        )
    ).one()
    transaction_rows = (
        await db.execute(
            select(BalanceTransaction, Market.question, Market.prompt)
            .outerjoin(Prediction, Prediction.id == BalanceTransaction.prediction_id)
            .outerjoin(Market, Market.id == Prediction.market_id)
            .where(BalanceTransaction.user_id == user.id)
            .order_by(BalanceTransaction.created_at.desc())
            .limit(200)
        )
    ).all()
    return _wallet_out(
        user,
        (int(total_stakes), int(total_payouts), int(net_pnl)),
        list(transaction_rows),
    )


def _profile_stats(rows: list) -> ProfileStatsOut:
    """Calculate profile metrics from rows shared by stats and bootstrap."""
    predictions = [prediction for prediction, _ in rows]
    revealed = [prediction for prediction in predictions if prediction.revealed_at]
    wins = [prediction for prediction in revealed if (prediction.pnl_cents or 0) >= 0]
    losses = [prediction for prediction in revealed if (prediction.pnl_cents or 0) < 0]

    current_streak = 0
    for prediction in reversed(revealed):
        if (prediction.pnl_cents or 0) >= 0:
            current_streak += 1
        else:
            break
    longest_streak = 0
    running = 0
    for prediction in revealed:
        if (prediction.pnl_cents or 0) >= 0:
            running += 1
            longest_streak = max(longest_streak, running)
        else:
            running = 0

    category_pnl: dict[str, int] = defaultdict(int)
    for prediction, category_name in rows:
        if prediction.revealed_at:
            category_pnl[category_name] += prediction.pnl_cents or 0
    best_category = max(category_pnl, key=category_pnl.get) if category_pnl else None

    activity_counts = Counter(prediction.locked_at.date().isoformat() for prediction in predictions)
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=83)
    activity = [
        ActivityDayOut(
            date=(start_date + timedelta(days=offset)).isoformat(),
            markets_played=activity_counts[(start_date + timedelta(days=offset)).isoformat()],
        )
        for offset in range(84)
    ]
    return ProfileStatsOut(
        markets_played=len(predictions),
        revealed=len(revealed),
        pending=len(predictions) - len(revealed),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(revealed) if revealed else 0,
        average_accuracy=(
            sum(prediction.accuracy_score or 0 for prediction in revealed) / len(revealed)
            if revealed else 0
        ),
        total_pnl_cents=sum(prediction.pnl_cents or 0 for prediction in revealed),
        total_volume_cents=sum(prediction.stake_cents or 0 for prediction in predictions),
        biggest_win_cents=max(0, max((prediction.pnl_cents or 0 for prediction in revealed), default=0)),
        current_streak=current_streak,
        longest_streak=longest_streak,
        best_category=best_category,
        activity=activity,
    )


def _null_like(column):
    return literal(None, type_=column.type)


def _bootstrap_statement(user_id):
    """Fetch compact prediction summaries and wallet rows in one round trip."""
    prediction_rows = (
        select(
            literal("prediction").label("row_kind"),
            Prediction.id.label("row_id"),
            Category.name.label("category_name"),
            Prediction.stake_cents.label("stake_cents"),
            Prediction.payout_cents.label("payout_cents"),
            Prediction.settled_at.label("settled_at"),
            Prediction.revealed_at.label("revealed_at"),
            Prediction.pnl_cents.label("pnl_cents"),
            Prediction.accuracy_score.label("accuracy_score"),
            Prediction.locked_at.label("locked_at"),
            _null_like(BalanceTransaction.transaction_type).label("transaction_type"),
            _null_like(BalanceTransaction.amount_cents).label("amount_cents"),
            _null_like(BalanceTransaction.balance_after_cents).label("balance_after_cents"),
            _null_like(BalanceTransaction.prediction_id).label("transaction_prediction_id"),
            _null_like(Market.question).label("question"),
            _null_like(BalanceTransaction.created_at).label("created_at"),
        )
        .join(Market, Market.id == Prediction.market_id)
        .join(Category, Category.id == Market.category_id)
        .where(
            Prediction.user_id == user_id,
            Market.market_kind == PULSE_MARKET_KIND,
        )
    )
    transaction_rows = (
        select(
            literal("transaction").label("row_kind"),
            BalanceTransaction.id.label("row_id"),
            _null_like(Category.name).label("category_name"),
            _null_like(Prediction.stake_cents).label("stake_cents"),
            _null_like(Prediction.payout_cents).label("payout_cents"),
            _null_like(Prediction.settled_at).label("settled_at"),
            _null_like(Prediction.revealed_at).label("revealed_at"),
            _null_like(Prediction.pnl_cents).label("pnl_cents"),
            _null_like(Prediction.accuracy_score).label("accuracy_score"),
            _null_like(Prediction.locked_at).label("locked_at"),
            BalanceTransaction.transaction_type.label("transaction_type"),
            BalanceTransaction.amount_cents.label("amount_cents"),
            BalanceTransaction.balance_after_cents.label("balance_after_cents"),
            BalanceTransaction.prediction_id.label("transaction_prediction_id"),
            func.coalesce(Market.question, Market.prompt).label("question"),
            BalanceTransaction.created_at.label("created_at"),
        )
        .outerjoin(Prediction, Prediction.id == BalanceTransaction.prediction_id)
        .outerjoin(Market, Market.id == Prediction.market_id)
        .where(BalanceTransaction.user_id == user_id)
    )
    return union_all(prediction_rows, transaction_rows)


def _split_bootstrap_rows(rows: list) -> tuple[list, list]:
    predictions = []
    transactions = []
    for row in rows:
        item = row._mapping
        if item["row_kind"] == "prediction":
            predictions.append(
                SimpleNamespace(
                    id=item["row_id"],
                    stake_cents=item["stake_cents"],
                    payout_cents=item["payout_cents"],
                    settled_at=item["settled_at"],
                    revealed_at=item["revealed_at"],
                    pnl_cents=item["pnl_cents"],
                    accuracy_score=item["accuracy_score"],
                    locked_at=item["locked_at"],
                    category_name=item["category_name"],
                )
            )
        else:
            transactions.append(
                (
                    SimpleNamespace(
                        id=item["row_id"],
                        transaction_type=item["transaction_type"],
                        amount_cents=item["amount_cents"],
                        balance_after_cents=item["balance_after_cents"],
                        prediction_id=item["transaction_prediction_id"],
                        created_at=item["created_at"],
                    ),
                    item["question"],
                    None,
                )
            )
    predictions.sort(key=lambda prediction: prediction.locked_at)
    transactions.sort(key=lambda item: item[0].created_at, reverse=True)
    return predictions, transactions[:200]


@router.get("/me/stats", response_model=ProfileStatsOut)
async def stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Prediction, Category.name)
            .join(Market, Market.id == Prediction.market_id)
            .join(Category, Category.id == Market.category_id)
            .where(
                Prediction.user_id == user.id,
                Market.market_kind == PULSE_MARKET_KIND,
            )
            .order_by(Prediction.locked_at)
        )
    ).all()
    return _profile_stats(list(rows))


@router.get("/bootstrap", response_model=AppBootstrapOut)
async def bootstrap(
    user: User = Depends(get_current_user_with_categories),
    db: AsyncSession = Depends(get_db),
):
    """Load the signed-in shell and summary screens with one data query."""
    rows = (await db.execute(_bootstrap_statement(user.id))).all()
    predictions, transaction_rows = _split_bootstrap_rows(list(rows))
    prediction_rows = [
        (prediction, prediction.category_name) for prediction in predictions
    ]
    return AppBootstrapOut(
        user=_user_out(user),
        profile_stats=_profile_stats(prediction_rows),
        wallet=_wallet_out(user, _wallet_totals(predictions), list(transaction_rows)),
        leaderboard=build_leaderboard(user, predictions),
    )
