import assert from "node:assert/strict";
import test from "node:test";
import { orderMarketsForDeck } from "./feedDeck.js";

function market(id, category, revealSeconds) {
  return {
    id,
    reveal_seconds: revealSeconds,
    category: { id: category, slug: category },
  };
}

test("markets with the same closing time are interleaved by category", () => {
  const ordered = orderMarketsForDeck([
    market("music-1", "music", 60),
    market("music-2", "music", 60),
    market("music-3", "music", 60),
    market("sport-1", "sports", 60),
    market("sport-2", "sports", 60),
    market("film-1", "film", 60),
    market("film-2", "film", 60),
  ]);

  assert.deepEqual(
    ordered.map((item) => item.id),
    ["music-1", "sport-1", "film-1", "music-2", "sport-2", "film-2", "music-3"],
  );
});
test("earlier closing markets stay ahead of later closing markets", () => {
  const ordered = orderMarketsForDeck([
    market("music-later", "music", 90),
    market("sport-first", "sports", 30),
    market("film-next", "film", 60),
    market("music-first", "music", 30),
  ]);

  assert.deepEqual(
    ordered.map((item) => item.id),
    ["sport-first", "music-first", "film-next", "music-later"],
  );
});
