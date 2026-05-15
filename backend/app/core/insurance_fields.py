"""
Insurance domain configuration.

Modify CRITICAL_FIELDS to match your specific data model.
Modify SCORING_CONFIG to tune the reliability scoring framework.

Both are intentionally kept as plain Python dicts/sets so they are easy to
override from a config file, database, or environment variable in the future.
"""

# ── Critical insurance fields ──────────────────────────────────────────────
# If these columns are null or malformed they attract a heavy extra penalty
# on top of the normal null-rate deduction.  Add or remove fields to match
# the datasets your customers upload.
CRITICAL_FIELDS: set[str] = {
    "policy_number",
    "premium",
    "ncd",
    "inception_date",
    "expiry_date",
    "postcode",
    "product_type",
    "claim_id",
    "claim_amount",
}

# ── Column-name hints ──────────────────────────────────────────────────────
# Used by profiling.py to infer the semantic type of a column before any
# value-level inspection.

DATE_COLUMN_KEYWORDS: list[str] = [
    "date",
    "time",
    "inception",
    "expiry",
    "created",
    "updated",
    "issued",
    "effective",
]

IDENTIFIER_COLUMN_KEYWORDS: list[str] = [
    "id",
    "number",
    "ref",
    "code",
    "key",
    "no",
]

# ── Scoring framework ──────────────────────────────────────────────────────
# All thresholds are rates in [0.0, 1.0].  Penalties are absolute points
# deducted from a starting score of 100.  Penalty lists must be ordered
# highest-threshold-first so the correct tier is selected quickly.
SCORING_CONFIG: dict = {
    # Applied per column — picks the highest tier the null rate exceeds.
    "null_penalties": [
        {"threshold": 0.50, "penalty": 10},   # > 50 % null
        {"threshold": 0.20, "penalty": 5},    # > 20 % null
        {"threshold": 0.05, "penalty": 2},    # >  5 % null
    ],
    # Applied in addition to the normal null penalty when the column is in
    # CRITICAL_FIELDS and has at least one null.
    "critical_field_null_penalty": 15,

    # Applied once per dataset — duplicate row penalties.
    "duplicate_penalties": [
        {"threshold": 0.05, "penalty": 20},   # > 5 % duplicate rows
        {"threshold": 0.01, "penalty": 10},   # > 1 % duplicate rows
    ],

    # Per-column format penalties.
    "format_inconsistency_penalty": 3,       # mixed casing in categorical column
    "date_format_inconsistency_penalty": 5,  # > 1 date format pattern detected
    "invalid_date_penalty": 2,               # per column with un-parseable date values

    # Numeric outlier penalty (applied if outlier rate exceeds threshold).
    "outlier_penalty": 3,
    "outlier_rate_threshold": 0.05,          # 5 % of values are statistical outliers

    # Grade thresholds (inclusive lower bound).
    "grade": {
        "green": 80,
        "amber": 60,
        # Below amber → Red
    },
}

# ── Cross-dataset fill configuration ──────────────────────────────────────

# Columns excluded from cross-dataset null filling even if they share a name
# across datasets.  These often carry dataset-specific meanings (e.g. "status"
# means "Active/Lapsed" in policies but "Open/Closed" in claims).
CROSS_DATASET_FILL_EXCLUSIONS: set[str] = {
    "status",
    "description",
    "notes",
    "comments",
    "remarks",
}

# Minimum uniqueness ratio a column must have in BOTH datasets to qualify as a
# join key.  Raise to 0.90+ for stricter matching; lower to 0.70 for messier data.
JOIN_KEY_MIN_UNIQUENESS: float = 0.80

# Maximum null rate a column may have in BOTH datasets to qualify as a join key.
JOIN_KEY_MAX_NULL_PCT: float = 0.10

# Minimum uniqueness ratio that marks a join key as a true primary key.
# Proposals that use a primary join key receive a higher confidence score.
JOIN_KEY_PRIMARY_UNIQUENESS_THRESHOLD: float = 0.95

# Confidence assigned to cross-dataset fill proposals when the join key is a
# true primary key (uniqueness ≥ JOIN_KEY_PRIMARY_UNIQUENESS_THRESHOLD in both
# datasets).
CROSS_FILL_CONFIDENCE_PRIMARY: float = 0.90

# Confidence assigned to cross-dataset fill proposals when the join key has
# lower uniqueness (e.g. customer_id where one customer can have many policies).
CROSS_FILL_CONFIDENCE_SECONDARY: float = 0.75

# Column names that represent policy-level join keys (one row per policy).
# These are preferred over customer-level keys (one customer → many policies)
# to avoid incorrect cross-dataset fills.
PREFERRED_JOIN_KEYS: list[str] = [
    "policy_number",
    "claim_id",
    "quote_id",
    "policy_id",
    "claim_number",
    "quote_number",
]

# ── Interpolation configuration ────────────────────────────────────────────

# Column name pairs where a simple annual date inference is valid.
# If one column is present and non-null, the other can be inferred as ± 1 year.
ANNUAL_DATE_PAIRS: list[tuple[str, str]] = [
    ("inception_date", "expiry_date"),
]

# Minimum number of complete (both-dates-filled) rows required before the
# annual date inference rule fires.  Prevents inference on tiny datasets.
DATE_INFERENCE_MIN_SAMPLE_ROWS: int = 3

# Minimum proportion of complete rows that must confirm an annual policy term
# (365–366 days) before proposing date inference for any null row.
DATE_INFERENCE_MIN_ANNUAL_RATIO: float = 0.80

# Confidence assigned to annual date inference proposals.
DATE_INFERENCE_CONFIDENCE: float = 0.75

# ── Sequential identifier inference ────────────────────────────────────────
# Applies only when: a column is inferred as 'identifier', the dataset has an
# ordering column (see TIMESTAMP_COLUMN_KEYWORDS), and exactly one null falls
# between two consecutive IDs that differ by exactly one in their numeric part.

# Confidence is intentionally medium — structural ordering supports the gap
# but does not prove the sequence was intentional.
SEQUENTIAL_ID_CONFIDENCE: float = 0.65

# Column names that indicate a time-ordering dimension suitable for sorting
# before applying the sequential ID inference rule.
TIMESTAMP_COLUMN_KEYWORDS: list[str] = [
    "timestamp",
    "created_at",
    "created",
    "quote_time",
    "transaction_time",
    "event_time",
    "recorded_at",
    "logged_at",
    "datetime",
]

# ── Analyst business rules ──────────────────────────────────────────────────
# Default thresholds used by data_corrections.py when no analyst rules are
# supplied at upload time.  The upload route now accepts analyst_rules as a
# JSON form field that overrides these defaults per session.

ANALYST_RULES: dict = {
    # Premiums below this value are flagged for analyst review.
    "minimum_premium": 50.0,
    # Optional upper bound on premium.  None disables ceiling check.
    "maximum_premium": None,
    # Maximum credible NCD years.  None disables the check.
    "max_ncd": None,
    # Output format for date-format correction proposals.
    # Uses Python strftime codes.  Default maps to DD-MM-YY.
    "date_format_standard": "%d-%m-%y",
    # Currency symbol used when displaying / normalising money values.
    "currency_symbol": "£",
}

# ── Column name sets for data correction rules ──────────────────────────────
# Used by data_corrections.py to locate insurance-specific columns by name.
# All comparisons are case-insensitive (column names are lowercased before
# matching).

# Columns that should always be uppercased and stripped.
POSTCODE_COLUMN_NAMES: frozenset[str] = frozenset({
    "postcode", "post_code", "zip", "zip_code", "postal_code",
})

# Columns whose casing should be normalised to the majority style.
PRODUCT_TYPE_COLUMN_NAMES: frozenset[str] = frozenset({
    "product_type", "product", "cover_type", "coverage_type", "policy_type",
})

# Columns that may contain currency-formatted strings (e.g. "£1,200").
CURRENCY_COLUMN_NAMES: frozenset[str] = frozenset({
    "premium", "gross_premium", "net_premium", "annual_premium",
    "claim_amount", "amount", "sum_insured",
})

# Subset of CURRENCY_COLUMN_NAMES where a floor check is applied.
PREMIUM_COLUMN_NAMES: frozenset[str] = frozenset({
    "premium", "gross_premium", "net_premium", "annual_premium",
})

# Columns that represent No Claims Discount / No Claims Bonus.
# Used by _ncd_ceiling_proposals in data_corrections.py.
NCD_COLUMN_NAMES: frozenset[str] = frozenset({
    "ncd", "ncd_years", "ncb", "ncb_years",
    "no_claims_discount", "no_claims_bonus",
})
