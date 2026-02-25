"""Schema contract validation for IronLayer models.

This module provides compile-time enforcement of column-type contracts
declared in SQL model headers.  Violations are detected at plan time and
surfaced in the plan preview.
"""

from core_engine.contracts.schema_validator import (
    ContractValidationResult,
    ContractViolation,
    ViolationSeverity,
    validate_schema_contract,
)

__all__ = [
    "ContractValidationResult",
    "ContractViolation",
    "ViolationSeverity",
    "validate_schema_contract",
]
