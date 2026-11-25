"""Servicios de dominio y puentes desacoplados para la API SIAMA."""

from src.api.services.imputation_bridge import enforce_physical_bounds, predict_on_demand

__all__ = ["enforce_physical_bounds", "predict_on_demand"]
