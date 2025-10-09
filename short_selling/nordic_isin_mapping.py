#!/usr/bin/env python3
"""
ISIN Mapping for Nordic Stocks

Provides ISIN codes for common Nordic stocks traded on:
- Stockholm (ST)
- Helsinki (HE)
- Oslo (OL)  
- Copenhagen (CO)
"""

# Common Swedish stocks (ST)
SWEDISH_ISINS = {
    'ABB.ST': 'CH0012221716',
    'ALFA.ST': 'SE0000767188',
    'ALIV-SDB.ST': 'SE0017486889',
    'ALLEI.ST': 'SE0023436450',
    'ASSA-B.ST': 'SE0007100581',
    'ATCO-A.ST': 'SE0011166610',
    'ATCO-B.ST': 'SE0011166644',
    'AZN.ST': 'GB0009895292',
    'BILL.ST': 'SE0000862997',
    'BOL.ST': 'SE0000862926',
    'ELUX-B.ST': 'SE0016589188',
    'EPI-B.ST': 'SE0009656601',
    'ERIC-B.ST': 'SE0000108656',
    'EVO.ST': 'SE0012673267',
    'GETI-B.ST': 'SE0000163594',
    'HEXA-B.ST': 'SE0000103814',
    'HM-B.ST': 'SE0000106270',
    'HTRO.ST': 'SE0006993770',
    'INVE-B.ST': 'SE0015811963',
    'KINV-B.ST': 'SE0012455293',
    'NDA-SE.ST': 'SE0017486889',
    'NIBE-B.ST': 'SE0017486889',
    'SAAB-B.ST': 'SE0000112385',
    'SAND.ST': 'SE0000106205',
    'SCA-B.ST': 'SE0000112724',
    'SEB-A.ST': 'SE0000148884',
    'SHB-B.ST': 'SE0000148883',
    'SINCH.ST': 'SE0011645671',
    'SKA-B.ST': 'SE0000120186',
    'SKF-B.ST': 'SE0000108227',
    'SSAB-B.ST': 'SE0000171100',
    'SWED-A.ST': 'SE0000242455',
    'TEL2-B.ST': 'SE0005190238',
    'TELIA.ST': 'SE0000667925',
    'VISC.ST': 'SE0014504817',
    'VOLCAR-B.ST': 'SE0015961909',
    'VOLV-B.ST': 'SE0000115446',
}

# Finnish stocks (HE)
FINNISH_ISINS = {
    'FIA1S.HE': 'FI0009003727',
}

# Norwegian stocks (OL)
NORWEGIAN_ISINS = {
    'NAS.OL': 'NO0010096985',
}

# Danish stocks (CO)
DANISH_ISINS = {
    'DFDS.CO': 'DK0010260061',
}

# Combined mapping
ISIN_MAPPING = {}
ISIN_MAPPING.update(SWEDISH_ISINS)
ISIN_MAPPING.update(FINNISH_ISINS)
ISIN_MAPPING.update(NORWEGIAN_ISINS)
ISIN_MAPPING.update(DANISH_ISINS)


def get_isin(ticker: str) -> str:
    """Get ISIN for a ticker, returns None if not found."""
    return ISIN_MAPPING.get(ticker)


def get_ticker_from_isin(isin: str) -> str:
    """Get ticker for an ISIN, returns None if not found."""
    for ticker, ticker_isin in ISIN_MAPPING.items():
        if ticker_isin == isin:
            return ticker
    return None


def get_all_isins() -> dict:
    """Get all ISIN mappings."""
    return ISIN_MAPPING.copy()


if __name__ == "__main__":
    # Test the mappings
    print(f"Total ISINs mapped: {len(ISIN_MAPPING)}")
    print("\nSample mappings:")
    for ticker, isin in list(ISIN_MAPPING.items())[:5]:
        print(f"  {ticker}: {isin}")
