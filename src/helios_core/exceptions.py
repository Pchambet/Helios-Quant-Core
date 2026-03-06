"""
Custom exceptions for Helios-Quant-Core.
Enforces Fail Fast, Fail Loud principles for data ingestion.
"""


class DataIngestionError(Exception):
    """
    Raised when critical data cannot be fetched or attached.
    The pipeline MUST crash — do not proceed with incomplete or corrupted data.
    """

    pass
