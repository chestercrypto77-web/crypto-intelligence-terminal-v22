"""Stable AWS Lambda module entry point for V22.

AWS handler setting: ``v22.runtime.lambda_entry.lambda_handler``.
Keeping this wrapper tiny lets the deployment package and AWS configuration stay
stable while the internal Brain runtime evolves.
"""
from v22.runtime.lambda_adapter import lambda_handler

__all__ = ["lambda_handler"]
