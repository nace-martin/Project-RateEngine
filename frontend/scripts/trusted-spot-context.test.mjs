import assert from "node:assert/strict";
import fs from "node:fs";

const quoteHook = fs.readFileSync(new URL("../src/hooks/useQuoteLogic.ts", import.meta.url), "utf8");
const quoteDetail = fs.readFileSync(new URL("../src/app/quotes/[id]/page.tsx", import.meta.url), "utf8");

assert.match(
  quoteHook,
  /const persistedQuote = await onSubmit\(data\);[\s\S]*quote_id: persistedQuote\.quoteId/,
  "New Quote must be persisted before its SPOT envelope is created with quote_id.",
);
assert.match(
  quoteDetail,
  /createSpotEnvelope\(\{[\s\S]*quote_id: quote\.id/,
  "Quote Detail must create a SPOT envelope with the persisted quote_id.",
);
assert.doesNotMatch(
  quoteDetail,
  /createSpotEnvelope\(\{[\s\S]{0,300}shipment_context:/,
  "Quote Detail must not send a client-authored shipment snapshot.",
);
assert.match(
  quoteDetail,
  /quote\.spot_negotiation\?\.can_reopen === false/,
  "Quote Detail must not automatically reopen an SPE whose trusted context is stale.",
);
assert.match(
  quoteDetail,
  /contextChanged=\{spotContextChanged\}/,
  "Quote Detail must show the fresh-review state for a stale SPE.",
);
assert.match(
  quoteDetail,
  /function buildSpotWorkflowParams[\s\S]*origin_code: context\.originCode,[\s\S]*dest_code: context\.destinationCode/,
  "Quote Detail reopen must retain the trusted route display.",
);

console.log("trusted SPOT context launch checks passed");
