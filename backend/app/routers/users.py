from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, get_current_user_with_categories
from app.config import settings
from app.database import get_db
from app.game import PULSE_MARKET_KIND, simulate_crowd
from app.models import (
    BalanceTransaction,
    Category,
    Market,
    MarketOption,
    Prediction,
    User,
)
from app.schemas import (
    ActivityDayOut,
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


async def _options_by_market(
    db: AsyncSession, market_ids: list
) -> dict:
    if not market_ids:
        return {}
    options = (
        await db.execute(
            select(MarketOption)
            .where(MarketOption.market_id.in_(market_ids))
            .order_by(MarketOption.market_id, MarketOption.display_order)
        )
    ).scalars().all()
    grouped: dict = defaultdict(list)
    for option in options:
        grouped[option.market_id].append(option)
    return grouped


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
        )
    ).all()
    options_by_market = await _options_by_market(db, [market.id for _, market, _ in rows])
    now = datetime.now(timezone.utc)
    output: list[HistoryPredictionOut] = []
    for prediction, market, category in rows:
        options = options_by_market[market.id]
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
    predictions = (
        await db.execute(
            select(Prediction)
            .join(Market, Market.id == Prediction.market_id)
            .where(
                Prediction.user_id == user.id,
                Market.market_kind == PULSE_MARKET_KIND,
            )
        )
    ).scalars().all()
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
    total_stakes, total_payouts, net_pnl = _wallet_totals(predictions)
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
