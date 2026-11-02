"""Sector layer: Damodaran Industry Groups -> the programme's 12 focus sectors."""
from __future__ import annotations

import pandas as pd

FOCUS: dict[str, list[str]] = {
    "Electronics & Semiconductors": ["Semiconductor", "Semiconductor Equip", "Electronics (Consumer & Office)",
                                     "Electronics (General)", "Computers/Peripherals", "Telecom. Equipment"],
    "Pharma & Bulk Drugs": ["Drugs (Pharmaceutical)", "Drugs (Biotechnology)"],
    "Medical Devices": ["Healthcare Products"],
    "Auto, EV & Components": ["Auto & Truck", "Auto Parts"],
    "Specialty Steel & Metals": ["Steel", "Metals & Mining"],
    "Chemicals & Plastics": ["Chemical (Basic)", "Chemical (Diversified)", "Chemical (Specialty)",
                             "Rubber& Tires", "Packaging & Container"],
    "White Goods & Electricals": ["Electrical Equipment", "Furn/Home Furnishings", "Household Products"],
    "Aerospace & Defence": ["Aerospace/Defense"],
    "Shipbuilding & Marine": ["Shipbuilding & Marine"],
    "Textiles & Apparel": ["Apparel", "Shoe"],
    "Food Processing": ["Food Processing"],
    "Green Energy & Fuels": ["Green & Renewable Energy", "Oil/Gas (Production and Exploration)", "Power",
                             "Coal & Related Energy"],
}

# Damodaran `Country` -> market code used by the 20-market tradable universe.
COUNTRY_TO_MARKET: dict[str, str] = {
    "India": "IN", "United States": "US", "Japan": "JP", "South Korea": "KR",
    "Taiwan": "TW", "China": "CN", "Germany": "DE", "Canada": "CA",
    "Australia": "AU", "United Kingdom": "UK", "Hong Kong": "HK",
    "Singapore": "SG", "Sweden": "SE", "Brazil": "BR", "Switzerland": "CH",
    "Denmark": "DK", "Finland": "FI", "South Africa": "ZA", "Saudi Arabia": "SA",
}

INDIA_MARKET = "IN"


def industry_to_focus() -> dict[str, str]:
    """Flatten FOCUS into Industry Group -> FocusSector."""
    return {industry: sector for sector, industries in FOCUS.items() for industry in industries}


def tag_focus_sectors(damodaran: pd.DataFrame) -> pd.DataFrame:
    """Keep Damodaran rows in a focus sector; add `FocusSector` and `Market` (NaN when unmapped)."""
    mapping = industry_to_focus()
    tagged = damodaran[damodaran["Industry Group"].isin(mapping)].copy()
    tagged["FocusSector"] = tagged["Industry Group"].map(mapping)
    tagged["Market"] = tagged["Country"].map(COUNTRY_TO_MARKET)
    return tagged


def region_of(market: str) -> str:
    """India vs Foreign split used by the screen and the shortlist."""
    return "India" if market == INDIA_MARKET else "Foreign"
