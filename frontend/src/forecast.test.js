import assert from "node:assert/strict";
import test from "node:test";
import { equalAllocations, rebalanceAllocations } from "./forecast.js";

const options = Array.from({ length: 8 }, (_, index) => ({ id: `option-${index + 1}` }));

function total(allocations) {
  return Object.values(allocations).reduce((sum, value) => sum + value, 0);
}

test("equal allocations use whole percentages and total exactly 100%", () => {
  const allocations = equalAllocations(options);

  assert.equal(total(allocations), 10_000);
  assert.deepEqual(Object.values(allocations), [1300, 1300, 1300, 1300, 1200, 1200, 1200, 1200]);
});

test("adjusting any bar preserves the relative shape of the remainder", () => {
  const initial = {
    "option-1": 4000,
    "option-2": 3000,
    "option-3": 2000,
    "option-4": 1000,
  };
  const next = rebalanceAllocations(options.slice(0, 4), initial, "option-2", 20);

  assert.deepEqual(next, {
    "option-2": 2000,
    "option-1": 4600,
    "option-3": 2300,
    "option-4": 1100,
  });
  assert.equal(total(next), 10_000);
});

test("moving several different bars still totals exactly 100%", () => {
  let allocations = equalAllocations(options.slice(0, 4));
  allocations = rebalanceAllocations(options.slice(0, 4), allocations, "option-1", 44);
  allocations = rebalanceAllocations(options.slice(0, 4), allocations, "option-3", 31);
  allocations = rebalanceAllocations(options.slice(0, 4), allocations, "option-4", 7);

  assert.equal(total(allocations), 10_000);
  assert.equal(allocations["option-1"] % 100, 0);
  assert.equal(allocations["option-3"], 3400);
  assert.equal(allocations["option-4"], 700);
});

test("lowering a 100% bar redistributes the released percentage evenly", () => {
  const allIn = Object.fromEntries(options.slice(0, 4).map((option, index) => [
    option.id,
    index === 0 ? 10_000 : 0,
  ]));
  const next = rebalanceAllocations(options.slice(0, 4), allIn, "option-1", 40);

  assert.deepEqual(next, {
    "option-1": 4000,
    "option-2": 2000,
    "option-3": 2000,
    "option-4": 2000,
  });
});

test("a one-option market remains at 100%", () => {
  assert.deepEqual(
    rebalanceAllocations(options.slice(0, 1), { "option-1": 10_000 }, "option-1", 20),
    { "option-1": 10_000 },
  );
});

test("locked bars stay fixed while unlocked bars rebalance", () => {
  const initial = {
    "option-1": 4000,
    "option-2": 3000,
    "option-3": 2000,
    "option-4": 1000,
  };
  const next = rebalanceAllocations(
    options.slice(0, 4),
    initial,
    "option-3",
    35,
    ["option-1"],
  );

  assert.deepEqual(next, {
    "option-1": 4000,
    "option-3": 3500,
    "option-2": 1900,
    "option-4": 600,
  });
  assert.equal(total(next), 10_000);
});

test("locked allocations cap the available range of an unlocked bar", () => {
  const initial = {
    "option-1": 6000,
    "option-2": 2000,
    "option-3": 1000,
    "option-4": 1000,
  };
  const next = rebalanceAllocations(
    options.slice(0, 4),
    initial,
    "option-2",
    90,
    ["option-1"],
  );

  assert.deepEqual(next, {
    "option-1": 6000,
    "option-2": 4000,
    "option-3": 0,
    "option-4": 0,
  });
});

test("a locked target ignores adjustment attempts", () => {
  const initial = {
    "option-1": 6000,
    "option-2": 4000,
  };

  assert.equal(
    rebalanceAllocations(options.slice(0, 2), initial, "option-1", 20, ["option-1"]),
    initial,
  );
});

test("reducing a 100% bar redistributes one point at a time across every other bar", () => {
  const eightOptions = options.slice(0, 8);
  let allocations = Object.fromEntries(
    eightOptions.map((option) => [option.id, option.id === "option-3" ? 10_000 : 0]),
  );

  allocations = rebalanceAllocations(eightOptions, allocations, "option-3", 99);
  assert.deepEqual(
    eightOptions.map((option) => allocations[option.id]),
    [0, 0, 9900, 100, 0, 0, 0, 0],
  );

  allocations = rebalanceAllocations(eightOptions, allocations, "option-3", 98);
  assert.deepEqual(
    eightOptions.map((option) => allocations[option.id]),
    [0, 0, 9800, 100, 100, 0, 0, 0],
  );

  for (let target = 97; target >= 93; target -= 1) {
    allocations = rebalanceAllocations(eightOptions, allocations, "option-3", target);
  }
  assert.deepEqual(
    eightOptions.map((option) => allocations[option.id]),
    [100, 100, 9300, 100, 100, 100, 100, 100],
  );

  allocations = rebalanceAllocations(eightOptions, allocations, "option-3", 92);
  assert.deepEqual(
    eightOptions.map((option) => allocations[option.id]),
    [100, 100, 9200, 200, 100, 100, 100, 100],
  );
  assert.equal(total(allocations), 10_000);
});
