"""
Tray Code Mapping - Master data for plating stock number to tray code validation
This mapping is used by both Zone 1 and Zone 2 jig unloading processes
"""

# Tray-code dropdown values for ModelMaster.
TRAY_CODE_CHOICES = [
    ('NR', 'NR'),
    ('ND', 'ND'),
    ('NB', 'NB'),
    ('NL', 'NL'),
    ('JR', 'JR'),
    ('JD', 'JD'),
    ('JB', 'JB'),
    ('JL', 'JL'),
]

NORMAL_TRAY_CODES = {'NR', 'ND', 'NB', 'NL'}
JUMBO_TRAY_CODES = {'JR', 'JD', 'JB', 'JL'}

# Master data mapping: Plating Stock No -> (Tray Codes allowed, Tray Capacity, Tray Type)
TRAY_CODE_MASTER_DATA = {
    # Format: 'plating_stock_no': {'tray_codes': ['NR', 'ND', ...], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1/Zone2'}
    
    # ==================== NORMAL - 16/20 CAPACITY ====================
    # IPS Colors (Red) - Zone 1
    '2617SAA02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2617WAA02': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2617SAB02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2617WAB02': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2617WAC02': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2617YAC02/2N': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2617NAD02': {'tray_codes': ['NB'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2617SAD02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2617YAD02/2N': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2617NSA02': {'tray_codes': ['NB'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    
    '2648NAA02': {'tray_codes': ['NB'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648QAA02/BRN': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648SAA02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2648WAA02': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648YAA02/2N': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2648KAB02/RGSS': {'tray_codes': ['NL'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648QAB02/GUN': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648SAB02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2648WAB02': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648QAD02/BRN': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648SAD02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2648WAD02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648SAE02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2648WAE02': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648QAF02/BRN': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648SAF02': {'tray_codes': ['NR'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone1'},
    '2648WAF02': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    '2648QAE02/BRN': {'tray_codes': ['ND'], 'tray_type': 'Normal', 'capacity': 20, 'zone': 'Zone2'},
    
    # ==================== JUMBO - 12 CAPACITY ====================
    # IPS Colors (Red) - Zone 1
    '1805NAA02': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805SAA02': {'tray_codes': ['JR'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone1'},
    '1805WAA02': {'tray_codes': ['JD'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805NAD02': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805QAD02/GUN': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805SAD02': {'tray_codes': ['JR'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone1'},
    '1805NAK02': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805SAK02': {'tray_codes': ['JR'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone1'},
    '1805WAK02': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805YAK02/2N': {'tray_codes': ['JR'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone1'},
    '1805NAR02': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805QBK02/GUN': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805WBK02': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805QCL02/GUN': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    '1805QSP02/GUN': {'tray_codes': ['JB'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone2'},
    'B1805SAA02': {'tray_codes': ['JR'], 'tray_type': 'Jumbo', 'capacity': 12, 'zone': 'Zone1'},
}


def get_tray_codes_for_plating_stock(plating_stock_no):
    """
    Get allowed tray codes for a given plating stock number
    Returns: {
        'allowed_codes': ['NR', 'ND', ...],
        'tray_type': 'Normal' or 'Jumbo',
        'capacity': int,
        'zone': 'Zone1' or 'Zone2'
    }
    """
    plating_stock_no = (plating_stock_no or '').strip()
    if not plating_stock_no:
        return None

    mapping = dict(TRAY_CODE_MASTER_DATA.get(plating_stock_no, {}))

    # Prefer DB-backed ModelMaster.tray_code when available. The mapping above
    # is the seed/fallback; admin master data remains the runtime SSOT.
    try:
        from modelmasterapp.models import ModelMaster

        model_master = ModelMaster.objects.filter(
            plating_stk_no=plating_stock_no
        ).select_related('tray_type').first()
        tray_code = (getattr(model_master, 'tray_code', '') or '').strip().upper() if model_master else ''
        if tray_code:
            mapping['tray_codes'] = [tray_code]
            if model_master.tray_type:
                mapping['tray_type'] = model_master.tray_type.tray_type
            elif tray_code in NORMAL_TRAY_CODES:
                mapping['tray_type'] = 'Normal'
            elif tray_code in JUMBO_TRAY_CODES:
                mapping['tray_type'] = 'Jumbo'
            mapping['capacity'] = mapping.get('capacity') or (
                20 if tray_code in NORMAL_TRAY_CODES else 12 if tray_code in JUMBO_TRAY_CODES else model_master.tray_capacity or 0
            )
    except Exception:
        pass

    return mapping or None


def validate_tray_code_for_stock(tray_code_prefix, plating_stock_no):
    """
    Validate if tray code is allowed for a given plating stock number
    Returns: (is_valid: bool, message: str, tray_info: dict)
    """
    mapping = get_tray_codes_for_plating_stock(plating_stock_no)
    
    if not mapping:
        return False, f"Plating stock {plating_stock_no} not found in master data", None
    
    allowed_codes = mapping.get('tray_codes', [])  # Fixed: use 'tray_codes' not 'allowed_codes'
    zone = mapping.get('zone', '')
    
    # Check if tray code prefix is in the allowed list
    if tray_code_prefix not in allowed_codes:
        return False, f"Tray code {tray_code_prefix} not allowed for {plating_stock_no}. Allowed: {', '.join(allowed_codes)} ({zone})", mapping
    
    return True, f"Tray code {tray_code_prefix} is valid for {plating_stock_no}", mapping
