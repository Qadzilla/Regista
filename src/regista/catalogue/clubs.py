"""The catalogue's invented clubs (60, in 13 competitions) and the colours their kits are drawn from.

Every name here is invented: towns, grounds and clubs. Short names are 3 letters, unique across the catalogue, and never
one of the Regista League's six (ASH, BRO, CAL, DUN, EAS, FAI). Kits are drawn per competition by
``regista.catalogue.define`` from the palettes below, by the league's rule: primaries far apart, keeper colours distinct
from every primary and from each other (the renderer and the vision layer need two clearly different team colours).
"""

from __future__ import annotations

# competition id -> [(club slug, name, short name, town, ground)]
CLUBS: dict[str, list[tuple[str, str, str, str, str]]] = {
    "co_eng_sp_women": [
        ("holmeley", "Holmeley Women", "HLM", "Holmeley", "Mill Lane"),
        ("skelbrook", "Skelbrook Ladies", "SKB", "Skelbrook", "Beck Side"),
        ("marrowby", "Marrowby Town Women", "MRW", "Marrowby", "Croft Park"),
        ("oxenridge", "Oxenridge Women", "OXR", "Oxenridge", "Moor Edge"),
        ("wetherholme", "Wetherholme Rangers Women", "WTH", "Wetherholme", "Station Fields"),
    ],
    "co_eng_u18": [
        ("cradlemoor", "Cradlemoor Albion U18", "CRM", "Cradlemoor", "Albion Training Ground"),
        ("netherhatch", "Netherhatch Town U18", "NHT", "Netherhatch", "Hatch Lane"),
        ("pellbury", "Pellbury Wanderers U18", "PLB", "Pellbury", "The Copse"),
        ("stokewell", "Stokewell United U18", "SKW", "Stokewell", "Wellfield Academy Pitch"),
    ],
    "co_usa_col_men": [
        ("kestrel_bay", "Kestrel Bay College", "KBC", "Kestrel Bay", "Harlan Field"),
        ("northmoor", "Northmoor University", "NMU", "Northmoor", "Ridley Field"),
        ("saltmarsh", "Saltmarsh State", "SMS", "Saltmarsh", "Cove Field"),
        ("granite_hollow", "Granite Hollow College", "GHC", "Granite Hollow", "Quarry Field"),
        ("merrow_point", "Merrow Point University", "MPU", "Merrow Point", "Lantern Field"),
        ("whitlock_hill", "Whitlock Hill College", "WHC", "Whitlock Hill", "Elm Field"),
    ],
    "co_usa_col_women": [
        ("coralline", "Coralline University", "CRL", "Coralline", "Tidepool Field"),
        ("mesa_alta", "Mesa Alta College", "MSA", "Mesa Alta", "Sunfield"),
        ("redwood_crest", "Redwood Crest University", "RCU", "Redwood Crest", "Grove Field"),
        ("point_halcyon", "Point Halcyon College", "PHC", "Point Halcyon", "Marina Field"),
        ("san_aurelio", "San Aurelio State", "SAU", "San Aurelio", "Mission Field"),
    ],
    "co_esp_am_men": [
        ("torrevalle", "CF Torrevalle", "TVL", "Torrevalle", "Campo Municipal de Torrevalle"),
        ("benialcor", "UD Benialcor", "BNC", "Benialcor", "Camp de l'Horta"),
        ("riuseca", "CD Riuseca", "RSC", "Riuseca", "Campo El Barranc"),
        ("montesol", "Atlético Montesol", "AMS", "Montesol", "Estadio Las Lomas"),
        ("fuentealba", "SD Fuentealba", "FTA", "Fuentealba", "Campo La Fuente"),
    ],
    "co_esp_u19": [
        ("valdecarro", "CD Valdecarro Juvenil", "VDC", "Valdecarro", "Campo Los Chopos"),
        ("sotoalto", "UD Sotoalto Juvenil", "SOT", "Sotoalto", "Ciudad Deportiva de Sotoalto"),
        ("penaroble", "Club Peñaroble Juvenil", "PNR", "Peñaroble", "Campo La Peña"),
        ("navalcastro", "CF Navalcastro Juvenil", "NVC", "Navalcastro", "Campo Municipal de Navalcastro"),
        ("pinarejo", "Atlético Pinarejo Juvenil", "PIJ", "Pinarejo", "Campo El Pinar"),
    ],
    "co_ger_sp_men": [
        ("hollenburg", "SV Hollenburg", "HBG", "Hollenburg", "Sportpark am Deich"),
        ("vorstadt", "FC Vorstadt 09", "VOR", "Vorstadt", "Stadion an der Weser"),
        ("lindenmoor", "TuS Lindenmoor", "LMR", "Lindenmoor", "Lindenstadion"),
        ("erlenhorst", "SC Erlenhorst", "EHR", "Erlenhorst", "Waldsportplatz"),
        ("moevenstedt", "VfL Mövenstedt", "MVS", "Mövenstedt", "Sportplatz Mühlenweg"),
        ("haselbrock", "Eintracht Haselbrock", "HSB", "Haselbrock", "Haselbrocker Kampfbahn"),
    ],
    "co_bra_u20": [
        ("pedra_alta", "EC Pedra Alta Sub-20", "EPA", "Pedra Alta", "Estádio da Serra"),
        ("lagoa_clara", "Grêmio Lagoa Clara Sub-20", "GLC", "Lagoa Clara", "Campo da Lagoa"),
        ("ribeirao_novo", "Atlético Ribeirão Novo Sub-20", "ARN", "Ribeirão Novo", "Estádio do Ribeirão"),
        ("morro_azul", "União Morro Azul Sub-20", "UMA", "Morro Azul", "Campo do Morro"),
    ],
    "co_nga_am_men": [
        ("adire_stars", "Adire Stars FC", "ADS", "Odoyemi", "Odoyemi Township Stadium"),
        ("riverbank", "Riverbank Warriors FC", "RBW", "Agbeleku", "Riverside Park"),
        ("iroko_lions", "Iroko Lions FC", "IRK", "Irokoland", "Iroko Grounds"),
        ("palmgrove", "Palmgrove Rangers FC", "PGR", "Palmgrove", "Palmgrove Field"),
    ],
    "co_gha_u17": [
        ("kente_royals", "Kente Royals Academy", "KTR", "Asafoase", "Royals Park"),
        ("adinkra_stars", "Adinkra Stars Academy", "ADK", "Nkwantaso", "Adinkra Park"),
        ("cocoa_hill", "Cocoa Hill Colts", "CCH", "Cocoa Hill", "Hilltop Park"),
        ("rainforest", "Rainforest Eagles Academy", "RFE", "Abofrem", "Eagles Nest"),
    ],
    "co_jpn_uni_men": [
        ("kaigan", "Kaigan University", "KGU", "Kaigan", "Kaigan Campus Ground"),
        ("shiosai", "Shiosai Gakuin University", "SSG", "Shiosai", "Shiosai Field"),
        ("hamakaze", "Hamakaze University", "HMK", "Hamakaze", "Hamakaze Ground"),
        ("aozora", "Aozora University", "AOZ", "Aozora", "Aozora Park Field"),
    ],
    "co_mex_am_men": [
        ("los_encinos", "Atlético Los Encinos", "ALE", "Los Encinos", "Unidad Deportiva Los Encinos"),
        ("barranca_honda", "Deportivo Barranca Honda", "DBH", "Barranca Honda", "Campo La Barranca"),
        ("tierra_roja", "Unión Tierra Roja", "UTR", "Tierra Roja", "Campo Tierra Roja"),
        ("agave_azul", "Club Agave Azul", "AGA", "Agave Azul", "Cancha El Agave"),
    ],
    "co_mar_u19": [
        ("oued_zitoun", "Ittihad Oued Zitoun Juniors", "IOZ", "Oued Zitoun", "Terrain Oued Zitoun"),
        ("najm_atlas", "Najm Atlas Juniors", "NAJ", "Ain Najma", "Stade de l'Atlas"),
        ("nour_cedres", "Nour Cèdres Juniors", "NCJ", "Bab Cèdres", "Terrain des Cèdres"),
        ("jnane_vert", "Chabab Jnane Vert Juniors", "CJV", "Jnane Vert", "Terrain Jnane"),
    ],
}

RESERVED_SHORT_NAMES = frozenset({"ASH", "BRO", "CAL", "DUN", "EAS", "FAI"})   # the Regista League's six

# Kit colours. Primaries: hues far apart (red, navy, green, purple, orange, sky, yellow, white, black, teal, magenta,
# maroon, royal blue, olive). Keeper colours: loud or neutral shades that stand off every primary.
PRIMARIES = ("#C8102E", "#1E3A8A", "#00A650", "#6A0DAD", "#FF8C00", "#00B5E2", "#FFD100", "#FFFFFF", "#111111", "#008080",
             "#E4007C", "#7A1F2B", "#3A5FCD", "#6B7F1A")
GK_COLOURS = ("#C6FF00", "#FF1493", "#FFD700", "#9E9E9E", "#8B4513", "#00FFFF", "#FF6F00", "#1DB954", "#F5F5DC", "#4B0082",
              "#FF69B4", "#7FFFD4", "#DA70D6", "#40E0D0", "#B0C4DE", "#FFA07A", "#2F4F4F", "#ADFF2F")
SECONDARIES = ("#FFFFFF", "#111111", "#F5D90A", "#002147")
