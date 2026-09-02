"""
Harmonize Mumbai Local Train Timetable CSVs into standard GTFS specification.
Processes all 54 wide-format timetable CSVs, maps station acronyms, cleans timestamps,
handles midnight rollovers, computes monotonic stop sequences, and outputs a complete GTFS feed.
"""

import os
import re
import zipfile
import pandas as pd
import numpy as np
from pathlib import Path

# Paths
DATA_RAW_DIR = Path("data/mumbai/raw/Mumbai Local Train Time")
OUT_DIR = Path("data/mumbai/processed/train_gtfs")
OUT_ZIP = Path("data/mumbai/processed/train_gtfs.zip")

# Canonical Station Registry with high-precision coordinates (EPSG:4326)
STATION_REGISTRY = {
    # Western Railway (Churchgate - Dahanu Road)
    "STN_CCG": {"name": "Churchgate", "lat": 18.9352, "lon": 72.8277},
    "STN_MEL": {"name": "Marine Lines", "lat": 18.9438, "lon": 72.8239},
    "STN_CYR": {"name": "Charni Road", "lat": 18.9519, "lon": 72.8188},
    "STN_GTR": {"name": "Grant Road", "lat": 18.9632, "lon": 72.8159},
    "STN_BCL": {"name": "Mumbai Central", "lat": 18.9698, "lon": 72.8194},
    "STN_MX": {"name": "Mahalaxmi", "lat": 18.9827, "lon": 72.8237},
    "STN_PL": {"name": "Lower Parel", "lat": 18.9956, "lon": 72.8306},
    "STN_PBHD": {"name": "Prabhadevi", "lat": 19.0069, "lon": 72.8347},
    "STN_DDR_WR": {"name": "Dadar (WR)", "lat": 19.0178, "lon": 72.8431},
    "STN_MRU": {"name": "Matunga Road", "lat": 19.0275, "lon": 72.8447},
    "STN_MM": {"name": "Mahim Junction", "lat": 19.0406, "lon": 72.8440},
    "STN_BA": {"name": "Bandra", "lat": 19.0544, "lon": 72.8405},
    "STN_KHAR": {"name": "Khar Road", "lat": 19.0699, "lon": 72.8398},
    "STN_STC": {"name": "Santacruz", "lat": 19.0818, "lon": 72.8402},
    "STN_VLP": {"name": "Vile Parle", "lat": 19.0988, "lon": 72.8439},
    "STN_ADH": {"name": "Andheri", "lat": 19.1197, "lon": 72.8464},
    "STN_JOS": {"name": "Jogeshwari", "lat": 19.1362, "lon": 72.8490},
    "STN_RMM": {"name": "Ram Mandir", "lat": 19.1517, "lon": 72.8493},
    "STN_GMN": {"name": "Goregaon", "lat": 19.1648, "lon": 72.8492},
    "STN_MDD": {"name": "Malad", "lat": 19.1866, "lon": 72.8488},
    "STN_KILE": {"name": "Kandivali", "lat": 19.2045, "lon": 72.8524},
    "STN_BVI": {"name": "Borivali", "lat": 19.2294, "lon": 72.8574},
    "STN_DIC": {"name": "Dahisar", "lat": 19.2501, "lon": 72.8593},
    "STN_MIRA": {"name": "Mira Road", "lat": 19.2814, "lon": 72.8561},
    "STN_BYR": {"name": "Bhayandar", "lat": 19.3121, "lon": 72.8528},
    "STN_NIG": {"name": "Naigaon", "lat": 19.3517, "lon": 72.8471},
    "STN_BSR": {"name": "Vasai Road", "lat": 19.3812, "lon": 72.8397},
    "STN_NSP": {"name": "Nallasopara", "lat": 19.4178, "lon": 72.8188},
    "STN_VR": {"name": "Virar", "lat": 19.4542, "lon": 72.8115},
    "STN_VTN": {"name": "Vaitarna", "lat": 19.5165, "lon": 72.8291},
    "STN_SAH": {"name": "Saphale", "lat": 19.5786, "lon": 72.8217},
    "STN_KLV": {"name": "Kelve Road", "lat": 19.6263, "lon": 72.7981},
    "STN_PLG": {"name": "Palghar", "lat": 19.6974, "lon": 72.7667},
    "STN_UOI": {"name": "Umroli", "lat": 19.7423, "lon": 72.7601},
    "STN_BOR": {"name": "Boisar", "lat": 19.8009, "lon": 72.7594},
    "STN_VGN": {"name": "Vangaon", "lat": 19.8821, "lon": 72.7562},
    "STN_DRD": {"name": "Dahanu Road", "lat": 19.9722, "lon": 72.7422},

    # Central Railway Main Line (CSMT - Kalyan - Kasara / Khopoli)
    "STN_CSMT": {"name": "Mumbai CSMT", "lat": 18.9400, "lon": 72.8353},
    "STN_MSD": {"name": "Masjid", "lat": 18.9525, "lon": 72.8383},
    "STN_SNRD": {"name": "Sandhurst Road", "lat": 18.9619, "lon": 72.8399},
    "STN_BY": {"name": "Byculla", "lat": 18.9768, "lon": 72.8336},
    "STN_CHG": {"name": "Chinchpokli", "lat": 18.9904, "lon": 72.8329},
    "STN_CRD": {"name": "Currey Road", "lat": 18.9961, "lon": 72.8324},
    "STN_PR": {"name": "Parel", "lat": 19.0084, "lon": 72.8373},
    "STN_DDR_CR": {"name": "Dadar (CR)", "lat": 19.0178, "lon": 72.8431},
    "STN_MTN": {"name": "Matunga", "lat": 19.0287, "lon": 72.8524},
    "STN_SIN": {"name": "Sion", "lat": 19.0392, "lon": 72.8624},
    "STN_CLA": {"name": "Kurla", "lat": 19.0664, "lon": 72.8797},
    "STN_VVH": {"name": "Vidyavihar", "lat": 19.0798, "lon": 72.8970},
    "STN_GC": {"name": "Ghatkopar", "lat": 19.0864, "lon": 72.9081},
    "STN_VK": {"name": "Vikhroli", "lat": 19.1106, "lon": 72.9284},
    "STN_KJMG": {"name": "Kanjurmarg", "lat": 19.1278, "lon": 72.9348},
    "STN_BND": {"name": "Bhandup", "lat": 19.1437, "lon": 72.9372},
    "STN_NHU": {"name": "Nahur", "lat": 19.1554, "lon": 72.9461},
    "STN_MLND": {"name": "Mulund", "lat": 19.1726, "lon": 72.9563},
    "STN_TNA": {"name": "Thane", "lat": 19.1860, "lon": 72.9759},
    "STN_KLVA": {"name": "Kalwa", "lat": 19.2001, "lon": 72.9964},
    "STN_MBQ": {"name": "Mumbra", "lat": 19.1906, "lon": 73.0232},
    "STN_DIVA": {"name": "Diva Junction", "lat": 19.1887, "lon": 73.0426},
    "STN_KOPR": {"name": "Kopar", "lat": 19.2139, "lon": 73.0782},
    "STN_DI": {"name": "Dombivli", "lat": 19.2184, "lon": 73.0867},
    "STN_THK": {"name": "Thakurli", "lat": 19.2274, "lon": 73.1009},
    "STN_KYN": {"name": "Kalyan Junction", "lat": 19.2364, "lon": 73.1305},
    "STN_SHAD": {"name": "Shahad", "lat": 19.2558, "lon": 73.1517},
    "STN_ABY": {"name": "Ambivli", "lat": 19.2736, "lon": 73.1678},
    "STN_TLA": {"name": "Titwala", "lat": 19.3005, "lon": 73.2081},
    "STN_KDV": {"name": "Khadavli", "lat": 19.3486, "lon": 73.2384},
    "STN_VSD": {"name": "Vasind", "lat": 19.4005, "lon": 73.2662},
    "STN_ASO": {"name": "Asangaon", "lat": 19.4414, "lon": 73.3082},
    "STN_ATG": {"name": "Atgaon", "lat": 19.5161, "lon": 73.3442},
    "STN_KDI": {"name": "Khardi", "lat": 19.5855, "lon": 73.3962},
    "STN_KSRA": {"name": "Kasara", "lat": 19.6528, "lon": 73.4831},
    "STN_VLDI": {"name": "Vithalwadi", "lat": 19.2259, "lon": 73.1444},
    "STN_ULNR": {"name": "Ulhasnagar", "lat": 19.2167, "lon": 73.1594},
    "STN_ABH": {"name": "Ambernath", "lat": 19.1994, "lon": 73.1897},
    "STN_BUD": {"name": "Badlapur", "lat": 19.1558, "lon": 73.2322},
    "STN_VGI": {"name": "Vangani", "lat": 19.0967, "lon": 73.2986},
    "STN_SHLU": {"name": "Shelu", "lat": 19.0628, "lon": 73.3283},
    "STN_NRL": {"name": "Neral Junction", "lat": 19.0272, "lon": 73.3197},
    "STN_BVS": {"name": "Bhivpuri Road", "lat": 18.9722, "lon": 73.3325},
    "STN_KJT": {"name": "Karjat", "lat": 18.9103, "lon": 73.3228},
    "STN_PDI": {"name": "Palasdhari", "lat": 18.8789, "lon": 73.3175},
    "STN_KLY": {"name": "Kelavli", "lat": 18.8475, "lon": 73.2961},
    "STN_DLV": {"name": "Dolavli", "lat": 18.8286, "lon": 73.2842},
    "STN_LWJ": {"name": "Lowjee", "lat": 18.7981, "lon": 73.2725},
    "STN_KHPI": {"name": "Khopoli", "lat": 18.7844, "lon": 73.2647},

    # Harbour Line (CSMT - Vadala - Panvel / Goregaon)
    "STN_DKRD": {"name": "Dockyard Road", "lat": 18.9669, "lon": 72.8427},
    "STN_RRD": {"name": "Reay Road", "lat": 18.9758, "lon": 72.8436},
    "STN_CTGN": {"name": "Cotton Green", "lat": 18.9867, "lon": 72.8475},
    "STN_SVE": {"name": "Sewri", "lat": 18.9994, "lon": 72.8544},
    "STN_VDLR": {"name": "Vadala Road", "lat": 19.0169, "lon": 72.8589},
    "STN_GTBN": {"name": "GTB Nagar", "lat": 19.0306, "lon": 72.8647},
    "STN_CHF": {"name": "Chunabhatti", "lat": 19.0494, "lon": 72.8719},
    "STN_TKNG": {"name": "Tilak Nagar", "lat": 19.0669, "lon": 72.8942},
    "STN_CMBR": {"name": "Chembur", "lat": 19.0619, "lon": 72.9008},
    "STN_GV": {"name": "Govandi", "lat": 19.0553, "lon": 72.9150},
    "STN_MNKD": {"name": "Mankhurd", "lat": 19.0497, "lon": 72.9328},
    "STN_VSH": {"name": "Vashi", "lat": 19.0644, "lon": 72.9989},
    "STN_SNCR": {"name": "Sanpada", "lat": 19.0664, "lon": 73.0117},
    "STN_JNJ": {"name": "Juinagar", "lat": 19.0558, "lon": 73.0189},
    "STN_NEU": {"name": "Nerul", "lat": 19.0336, "lon": 73.0175},
    "STN_SWDV": {"name": "Seawoods - Darave", "lat": 19.0192, "lon": 73.0194},
    "STN_BEPR": {"name": "Belapur CBD", "lat": 19.0186, "lon": 73.0397},
    "STN_KHAG": {"name": "Kharghar", "lat": 19.0247, "lon": 73.0678},
    "STN_MANR": {"name": "Mansarovar", "lat": 19.0189, "lon": 73.0847},
    "STN_KNDS": {"name": "Khandeshwar", "lat": 19.0069, "lon": 73.0978},
    "STN_PNVL": {"name": "Panvel", "lat": 18.9892, "lon": 73.1207},
    "STN_KCE": {"name": "King's Circle", "lat": 19.0303, "lon": 72.8572},

    # Trans-Harbour Line (Thane - Vashi / Panvel)
    "STN_DIGH": {"name": "Digha Gaon", "lat": 19.1678, "lon": 72.9936},
    "STN_AIRL": {"name": "Airoli", "lat": 19.1558, "lon": 72.9972},
    "STN_RABE": {"name": "Rabale", "lat": 19.1367, "lon": 73.0039},
    "STN_GNSL": {"name": "Ghansoli", "lat": 19.1178, "lon": 73.0089},
    "STN_KPHN": {"name": "Kopar Khairane", "lat": 19.0969, "lon": 73.0117},
    "STN_TUH": {"name": "Turbhe", "lat": 19.0758, "lon": 73.0167},

    # Uran Line (Nerul / Belapur - Uran)
    "STN_BMDR": {"name": "Bamandongri", "lat": 18.9806, "lon": 73.0136},
    "STN_KARP": {"name": "Kharkopar", "lat": 18.9619, "lon": 73.0069},
    "STN_SMKR": {"name": "Shematikhar", "lat": 18.9322, "lon": 72.9867},
    "STN_NSEV": {"name": "Nhava Sheva", "lat": 18.9189, "lon": 72.9739},
    "STN_DRGI": {"name": "Dronagiri", "lat": 18.8958, "lon": 72.9514},
    "STN_URAN": {"name": "Uran City", "lat": 18.8772, "lon": 72.9436},
}

# Mapping raw labels & station variants to canonical stop_ids
NAME_TO_STOP_ID = {
    # Western Line
    "churchgate": "STN_CCG",
    "marine lines": "STN_MEL",
    "charni road": "STN_CYR",
    "grant road": "STN_GTR",
    "m'bai central": "STN_BCL",
    "m'bai central (l)": "STN_BCL",
    "m'bai central(l": "STN_BCL",
    "m'bai central(l)": "STN_BCL",
    "mumbai central": "STN_BCL",
    "mahalakshmi": "STN_MX",
    "mahalaxmi": "STN_MX",
    "lower parel": "STN_PL",
    "prabhadevi": "STN_PBHD",
    "dadar": "STN_DDR_WR",
    "matunga road": "STN_MRU",
    "mahim jn.": "STN_MM",
    "mahim jn": "STN_MM",
    "mahim": "STN_MM",
    "bandra": "STN_BA",
    "khar road": "STN_KHAR",
    "khar": "STN_KHAR",
    "santa cruz": "STN_STC",
    "santacruz": "STN_STC",
    "santacurtz": "STN_STC",
    "vile parle": "STN_VLP",
    "vileparle": "STN_VLP",
    "andheri": "STN_ADH",
    "jogeshwari": "STN_JOS",
    "jogeswari": "STN_JOS",
    "ram mandir": "STN_RMM",
    "ramnagar": "STN_RMM",
    "goregaon": "STN_GMN",
    "malad": "STN_MDD",
    "kandivali": "STN_KILE",
    "kandivli": "STN_KILE",
    "borivali": "STN_BVI",
    "dahisar": "STN_DIC",
    "mira road": "STN_MIRA",
    "bhayandar": "STN_BYR",
    "naigaon": "STN_NIG",
    "vasai road": "STN_BSR",
    "nalla sopara": "STN_NSP",
    "nallasopara": "STN_NSP",
    "virar": "STN_VR",
    "vaiterna": "STN_VTN",
    "vaitarna": "STN_VTN",
    "saphale": "STN_SAH",
    "kelve road": "STN_KLV",
    "palghar": "STN_PLG",
    "umroli": "STN_UOI",
    "boisar": "STN_BOR",
    "vangaon": "STN_VGN",
    "dahanu road": "STN_DRD",

    # Central Main Line
    "csmt": "STN_CSMT",
    "mumbai csmt": "STN_CSMT",
    "masjid": "STN_MSD",
    "sandhurst road": "STN_SNRD",
    "byculla": "STN_BY",
    "chinchpokli": "STN_CHG",
    "currey road": "STN_CRD",
    "parel": "STN_PR",
    "matunga": "STN_MTN",
    "sion": "STN_SIN",
    "kurla": "STN_CLA",
    "vidyavihar": "STN_VVH",
    "ghatkopar": "STN_GC",
    "vikhroli": "STN_VK",
    "kanjur marg": "STN_KJMG",
    "kanjurmarg": "STN_KJMG",
    "bhandup": "STN_BND",
    "nahur": "STN_NHU",
    "mulund": "STN_MLND",
    "thane": "STN_TNA",
    "tna": "STN_TNA",
    "kalva": "STN_KLVA",
    "kalwa": "STN_KLVA",
    "mumbra": "STN_MBQ",
    "diva": "STN_DIVA",
    "kopar": "STN_KOPR",
    "dombivli": "STN_DI",
    "thakurli": "STN_THK",
    "kalyan": "STN_KYN",
    "shahad": "STN_SHAD",
    "ambivli": "STN_ABY",
    "titwala": "STN_TLA",
    "khadavli": "STN_KDV",
    "vasind": "STN_VSD",
    "asangaon": "STN_ASO",
    "atgaon": "STN_ATG",
    "khardi": "STN_KDI",
    "kasara": "STN_KSRA",
    "vithalwadi": "STN_VLDI",
    "ulhas nagar": "STN_ULNR",
    "ulhasnagar": "STN_ULNR",
    "ambernath": "STN_ABH",
    "badlapur": "STN_BUD",
    "vangani": "STN_VGI",
    "shelu": "STN_SHLU",
    "neral": "STN_NRL",
    "bhivpuri road": "STN_BVS",
    "karjat": "STN_KJT",
    "palasdhari": "STN_PDI",
    "kelavli": "STN_KLY",
    "dolavli": "STN_DLV",
    "lowjee": "STN_LWJ",
    "khopoli": "STN_KHPI",

    # Harbour Line
    "dockyard road": "STN_DKRD",
    "dock yard road": "STN_DKRD",
    "reay road": "STN_RRD",
    "cotton green": "STN_CTGN",
    "sewri": "STN_SVE",
    "seweri": "STN_SVE",
    "vadala road": "STN_VDLR",
    "gtb nagar": "STN_GTBN",
    "chunabhatti": "STN_CHF",
    "tilaknagar": "STN_TKNG",
    "tilak nagar": "STN_TKNG",
    "chembur": "STN_CMBR",
    "govandi": "STN_GV",
    "mankhurd": "STN_MNKD",
    "vashi": "STN_VSH",
    "vsh": "STN_VSH",
    "sanpada": "STN_SNCR",
    "snpd": "STN_SNCR",
    "juinagar": "STN_JNJ",
    "jnj": "STN_JNJ",
    "nerul": "STN_NEU",
    "neu": "STN_NEU",
    "seawood darave": "STN_SWDV",
    "seawoods darave": "STN_SWDV",
    "swdv": "STN_SWDV",
    "belapur cbd": "STN_BEPR",
    "belapur": "STN_BEPR",
    "bepr": "STN_BEPR",
    "kharghar": "STN_KHAG",
    "khag": "STN_KHAG",
    "mansarovar": "STN_MANR",
    "manr": "STN_MANR",
    "khandeshwar": "STN_KNDS",
    "knds": "STN_KNDS",
    "panvel": "STN_PNVL",
    "pnvl": "STN_PNVL",
    "king's circle": "STN_KCE",

    # Trans-Harbour Line
    "digh": "STN_DIGH",
    "digha gaon": "STN_DIGH",
    "airl": "STN_AIRL",
    "airoli": "STN_AIRL",
    "rabe": "STN_RABE",
    "rabale": "STN_RABE",
    "gnsl": "STN_GNSL",
    "ghansoli": "STN_GNSL",
    "kphn": "STN_KPHN",
    "kopar khairane": "STN_KPHN",
    "tuh": "STN_TUH",
    "turbhe": "STN_TUH",

    # Uran Line
    "bamandongri": "STN_BMDR",
    "kharkopar": "STN_KARP",
    "shematikhar": "STN_SMKR",
    "nhave-sheva": "STN_NSEV",
    "nhava sheva": "STN_NSEV",
    "dronagiri": "STN_DRGI",
    "uran": "STN_URAN",
}

# Multi-station row mapping for table artifacts
MULTI_ROW_MAP = {
    "dahanu road vangaon boisar": ["dahanu road", "vangaon", "boisar"],
    "palghar kelve road": ["palghar", "kelve road"],
    "virar nallasopara": ["virar", "nallasopara"],
    "naigaon bhayandar": ["naigaon", "bhayandar"],
    "borivali andheri bandra": ["borivali", "andheri", "bandra"],
    "grant road charni road marine lines churchgate": ["grant road", "charni road", "marine lines", "churchgate"],
    "matunga road mahim jn. bandra": ["matunga road", "mahim jn.", "bandra"],
    "mahalakshmi lower parel prabhadevi dadar": ["mahalakshmi", "lower parel", "prabhadevi", "dadar"],
}

TIME_RE = re.compile(r"^\s*([0-2]?[0-9])[:.]([0-5][0-9])(?::([0-5][0-9]))?\s*$")
HEADER_KEYWORDS = [
    "train no", "train code", "stations", "tr.no", "harbour", "dn trains",
    "up trains", "dn hbr", "up hbr", "public time", "w.e.f", "table", "not on",
    "ladies", "special", "reserved", "services", "trans"
]

def is_header_val(val):
    if pd.isna(val):
        return False
    v = str(val).strip().lower()
    return any(k in v for k in HEADER_KEYWORDS)

def parse_time_seconds(val):
    """Parse time string and return total seconds from midnight."""
    if pd.isna(val):
        return None
    val_str = str(val).strip()
    m = TIME_RE.match(val_str)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        ss = int(m.group(3)) if m.group(3) else 0
        return hh * 3600 + mm * 60 + ss
    return None

def format_gtfs_time(seconds):
    """Convert total seconds from midnight into standard GTFS HH:MM:SS string."""
    hh = seconds // 3600
    mm = (seconds % 3600) // 60
    ss = seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"

def resolve_stop_id(raw_str):
    """Resolve a raw station string into a canonical GTFS stop_id."""
    clean = str(raw_str).strip().lower()
    if clean in NAME_TO_STOP_ID:
        return NAME_TO_STOP_ID[clean]
    # Fuzzy / substring matching fallback
    for name, stop_id in NAME_TO_STOP_ID.items():
        if name in clean or clean in name:
            return stop_id
    return None

def infer_route_id(stop_ids, file_name):
    """Derive corridor / route_id from the stops visited and source file."""
    f_lower = file_name.lower()
    stops_set = set(stop_ids)
    
    # Uran Line
    if any(s in stops_set for s in ["STN_BMDR", "STN_KARP", "STN_SMKR", "STN_NSEV", "STN_DRGI", "STN_URAN"]):
        return "ROUTE_URAN", "Uran Line", "Nerul/Belapur - Uran Local"
    
    # Trans-Harbour Line
    if any(s in stops_set for s in ["STN_DIGH", "STN_AIRL", "STN_RABE", "STN_GNSL", "STN_KPHN", "STN_TUH"]):
        return "ROUTE_THBR", "Trans-Harbour Line", "Thane - Vashi/Panvel Trans-Harbour Local"
    
    # Harbour Line
    if any(s in stops_set for s in ["STN_VDLR", "STN_GTBN", "STN_CHF", "STN_TKNG", "STN_CMBR", "STN_GV", "STN_MNKD", "STN_KCE"]):
        return "ROUTE_HBR", "Harbour Line", "Mumbai CSMT - Panvel/Goregaon Harbour Local"
    
    # Western Railway Main Line
    if any(s in stops_set for s in ["STN_CCG", "STN_MEL", "STN_CYR", "STN_GTR", "STN_MX", "STN_PL", "STN_PBHD", "STN_MRU", "STN_KHAR", "STN_STC", "STN_VLP", "STN_JOS", "STN_MDD", "STN_KILE", "STN_BVI", "STN_DIC", "STN_MIRA", "STN_BYR", "STN_NIG", "STN_BSR", "STN_NSP", "STN_VR", "STN_VTN", "STN_SAH", "STN_KLV", "STN_PLG", "STN_UOI", "STN_BOR", "STN_VGN", "STN_DRD"]):
        return "ROUTE_WR", "Western Line", "Churchgate - Borivali/Virar/Dahanu Western Local"
    
    # Central Railway Main Line
    if any(s in stops_set for s in ["STN_CSMT", "STN_MSD", "STN_SNRD", "STN_BY", "STN_CHG", "STN_CRD", "STN_PR", "STN_MTN", "STN_SIN", "STN_CLA", "STN_VVH", "STN_GC", "STN_VK", "STN_KJMG", "STN_BND", "STN_NHU", "STN_MLND", "STN_TNA", "STN_KLVA", "STN_MBQ", "STN_DIVA", "STN_KOPR", "STN_DI", "STN_THK", "STN_KYN", "STN_SHAD", "STN_ABY", "STN_TLA", "STN_KDV", "STN_VSD", "STN_ASO", "STN_ATG", "STN_KDI", "STN_KSRA", "STN_VLDI", "STN_ULNR", "STN_ABH", "STN_BUD", "STN_VGI", "STN_SHLU", "STN_NRL", "STN_BVS", "STN_KJT", "STN_PDI", "STN_KLY", "STN_DLV", "STN_LWJ", "STN_KHPI"]):
        return "ROUTE_CR", "Central Line", "Mumbai CSMT - Kalyan/Kasara/Khopoli Main Local"
        
    return "ROUTE_SUB", "Suburban Line", "Mumbai Suburban Local Service"

def process_table_file(file_path):
    """Parse a single timetable CSV file and return all valid train trip stops."""
    df = pd.read_csv(file_path, header=None, dtype=str)
    num_rows, num_cols = df.shape
    
    # Identify block headers
    block_starts = []
    for r in range(num_rows):
        val0 = df.iloc[r, 0]
        if is_header_val(val0):
            if not block_starts or r > block_starts[-1] + 1:
                block_starts.append(r)
    
    if not block_starts:
        block_starts = [0]
        
    trips_found = []
    
    for b_i, start_r in enumerate(block_starts):
        end_r = block_starts[b_i + 1] if b_i + 1 < len(block_starts) else num_rows
        sub_df = df.iloc[start_r:end_r].copy().reset_index(drop=True)
        
        # Find header rows at the top of the block
        header_row_indices = []
        for r in range(min(5, len(sub_df))):
            val0 = sub_df.iloc[r, 0]
            if is_header_val(val0) or pd.isna(val0) or str(val0).strip() == "":
                header_row_indices.append(r)
            else:
                break
                
        if not header_row_indices:
            header_row_indices = [0]
            
        station_df = sub_df.iloc[len(header_row_indices):].copy().reset_index(drop=True)
        
        # Parse each column (train)
        for col_idx in range(1, sub_df.shape[1]):
            train_desc_parts = []
            for hr in header_row_indices:
                val = sub_df.iloc[hr, col_idx]
                if pd.notna(val) and str(val).strip() and not is_header_val(val):
                    train_desc_parts.append(str(val).strip())
            
            raw_train_name = " ".join(train_desc_parts).strip()
            # Clean train name or fallback
            train_name = raw_train_name if raw_train_name else f"{file_path.stem}_B{b_i+1}_C{col_idx}"
            # Extract train number if available
            m_num = re.search(r"\b\d{4,5}\b", train_name)
            train_no = m_num.group(0) if m_num else f"TRN_{file_path.stem.replace(' ', '')}_{b_i+1}_{col_idx}"
            
            # Extract raw stops and times
            raw_trip_stops = []
            for s_r in range(len(station_df)):
                stn_name_raw = station_df.iloc[s_r, 0]
                if pd.isna(stn_name_raw) or is_header_val(stn_name_raw):
                    continue
                stn_clean = str(stn_name_raw).strip()
                t_val = parse_time_seconds(station_df.iloc[s_r, col_idx])
                
                if t_val is not None:
                    # Check for multi-station row expansion
                    stn_lower = stn_clean.lower()
                    if stn_lower in MULTI_ROW_MAP:
                        # Map to first available station in sequence
                        expanded = MULTI_ROW_MAP[stn_lower]
                        target_stn = expanded[0]
                        stop_id = resolve_stop_id(target_stn)
                    else:
                        stop_id = resolve_stop_id(stn_clean)
                        
                    if stop_id:
                        raw_trip_stops.append((stop_id, t_val))
            
            if len(raw_trip_stops) >= 2:
                # Deduplicate consecutive identical stops if any
                deduped = []
                for st, sec in raw_trip_stops:
                    if not deduped or deduped[-1][0] != st:
                        deduped.append((st, sec))
                
                if len(deduped) >= 2:
                    # Fix time monotonicity (handle midnight rollover)
                    fixed_stops = []
                    prev_sec = None
                    rollover_offset = 0
                    
                    for st, sec in deduped:
                        adj_sec = sec + rollover_offset
                        if prev_sec is not None and adj_sec < prev_sec:
                            # If drop is significant (e.g. > 10 hours), assume midnight rollover
                            if (prev_sec - adj_sec) > 36000:
                                rollover_offset += 86400
                                adj_sec = sec + rollover_offset
                            elif adj_sec < prev_sec:
                                # Minor discrepancy or same minute halt: enforce monotonic non-decreasing
                                adj_sec = prev_sec
                                
                        fixed_stops.append((st, adj_sec))
                        prev_sec = adj_sec
                    
                    trips_found.append({
                        "file": file_path.name,
                        "train_no": train_no,
                        "train_name": train_name,
                        "stops": fixed_stops
                    })
                    
    return trips_found

def generate_gtfs():
    """Main pipeline to parse all 54 timetables and output GTFS specifications."""
    print("=" * 70)
    print("MUMBAI SUBURBAN RAILWAY GTFS HARMONIZATION PIPELINE")
    print("=" * 70)
    
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(list(DATA_RAW_DIR.glob("*.csv")), key=lambda p: int(re.search(r"\d+", p.stem).group()))
    print(f"Discovered {len(csv_files)} timetable CSV files in {DATA_RAW_DIR}")
    
    all_trips = []
    for f in csv_files:
        trips = process_table_file(f)
        all_trips.extend(trips)
        
    print(f"Extracted total candidate trips: {len(all_trips)}")
    
    # 1. Generate agency.txt
    print("\n[1/6] Generating agency.txt...")
    agency_df = pd.DataFrame([{
        "agency_id": "CR_WR_SUB",
        "agency_name": "Mumbai Suburban Railway",
        "agency_url": "https://wr.indianrailways.gov.in",
        "agency_timezone": "Asia/Kolkata",
        "agency_lang": "en",
        "agency_phone": "139"
    }])
    agency_df.to_csv(OUT_DIR / "agency.txt", index=False)
    
    # 2. Generate calendar.txt
    print("[2/6] Generating calendar.txt...")
    calendar_df = pd.DataFrame([{
        "service_id": "DAILY",
        "monday": 1,
        "tuesday": 1,
        "wednesday": 1,
        "thursday": 1,
        "friday": 1,
        "saturday": 1,
        "sunday": 1,
        "start_date": "20260101",
        "end_date": "20261231"
    }])
    calendar_df.to_csv(OUT_DIR / "calendar.txt", index=False)
    
    # 3. Process Trips, Routes, Stop Times
    print("[3/6] Compiling Routes, Trips, and Stop Times...")
    routes_dict = {}
    trips_list = []
    stop_times_list = []
    used_stop_ids = set()
    
    for idx, trip in enumerate(all_trips, 1):
        trip_id = f"TRIP_{idx:05d}_{trip['train_no']}"
        stop_ids = [s[0] for s in trip["stops"]]
        
        # Route determination
        route_id, route_short, route_long = infer_route_id(stop_ids, trip["file"])
        if route_id not in routes_dict:
            routes_dict[route_id] = {
                "route_id": route_id,
                "agency_id": "CR_WR_SUB",
                "route_short_name": route_short,
                "route_long_name": route_long,
                "route_type": 2  # Rail
            }
            
        # Origin and Destination for headsign
        origin_name = STATION_REGISTRY[stop_ids[0]]["name"]
        dest_name = STATION_REGISTRY[stop_ids[-1]]["name"]
        headsign = f"{dest_name} Local"
        
        trips_list.append({
            "route_id": route_id,
            "service_id": "DAILY",
            "trip_id": trip_id,
            "trip_headsign": headsign,
            "trip_short_name": trip["train_no"],
            "direction_id": 0
        })
        
        # Build stop_times entries
        for seq, (st_id, sec) in enumerate(trip["stops"], 1):
            time_str = format_gtfs_time(sec)
            used_stop_ids.add(st_id)
            stop_times_list.append({
                "trip_id": trip_id,
                "arrival_time": time_str,
                "departure_time": time_str,
                "stop_id": st_id,
                "stop_sequence": seq,
                "pickup_type": 0,
                "drop_off_type": 0
            })
            
    # 4. Generate routes.txt
    print("[4/6] Generating routes.txt...")
    routes_df = pd.DataFrame(list(routes_dict.values()))
    routes_df.to_csv(OUT_DIR / "routes.txt", index=False)
    
    # 5. Generate trips.txt & stop_times.txt
    print("[5/6] Generating trips.txt & stop_times.txt...")
    trips_df = pd.DataFrame(trips_list)
    trips_df.to_csv(OUT_DIR / "trips.txt", index=False)
    
    stop_times_df = pd.DataFrame(stop_times_list)
    stop_times_df.to_csv(OUT_DIR / "stop_times.txt", index=False)
    
    # 6. Generate stops.txt
    print("[6/6] Generating stops.txt with high-precision coordinates...")
    stops_list = []
    for st_id in sorted(used_stop_ids):
        info = STATION_REGISTRY[st_id]
        stops_list.append({
            "stop_id": st_id,
            "stop_name": info["name"],
            "stop_lat": info["lat"],
            "stop_lon": info["lon"],
            "location_type": 0,
            "wheelchair_boarding": 0
        })
        
    stops_df = pd.DataFrame(stops_list)
    stops_df.to_csv(OUT_DIR / "stops.txt", index=False)
    
    # 7. Repackage into a clean GTFS zip feed
    print(f"\nPackaging GTFS feed archive to {OUT_ZIP}...")
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for txt_file in ["agency.txt", "calendar.txt", "routes.txt", "trips.txt", "stops.txt", "stop_times.txt"]:
            z.write(OUT_DIR / txt_file, arcname=txt_file)
            
    print("=" * 70)
    print("GTFS HARMONIZATION COMPLETE - SUMMARY METRICS:")
    print(f"  • Unique Stations (stops.txt):    {len(stops_df):,}")
    print(f"  • Transit Routes (routes.txt):     {len(routes_df):,}")
    print(f"  • Total Trips (trips.txt):         {len(trips_df):,}")
    print(f"  • Total Stop Times (stop_times.txt): {len(stop_times_df):,}")
    print(f"  • Destination Feed Zip:           {OUT_ZIP} ({OUT_ZIP.stat().st_size / 1024:.1f} KB)")
    print("=" * 70)

if __name__ == "__main__":
    generate_gtfs()
