# Data Model for AIR · Import · A2D — Deterministic currency & destination-fee policy

This feature does not introduce any new database models. The following data structures will be implemented as Python data classes.

## Policy

A `Policy` is a data class that represents a set of rules for determining the currency and fee menu for a quote.

- **`name`**: `str` - The name of the policy.
- **`rules`**: `list[Rule]` - A list of rules that define the policy.

## Recipe

A `Recipe` is a data class that represents a component of a policy, defining a specific calculation or rule.

- **`name`**: `str` - The name of the recipe.
- **`action`**: `Callable` - A function that implements the recipe's logic.

## Snapshot

A `Snapshot` is a data class that provides a machine-readable record of the policy decisions made during the quoting process.

- **`policy_name`**: `str` - The name of the policy that was applied.
- **`recipe_executions`**: `list[dict]` - A list of dictionaries, where each dictionary records the execution of a recipe.
