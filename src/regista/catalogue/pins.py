"""The catalogue's matches, pinned: the first 16 hex digits of each catalogue match's ``events.jsonl`` as
``regista.catalogue.build`` writes it, recorded on macOS (arm64, Python 3.13) with generator 0.7.1, for the catalogue as
of ``taxonomy.AS_OF`` (every uploaded match dated on or before it).

Like the Regista League's (``regista.season.pins``), catalogue matches are built on demand on the server (Linux,
Python 3.11, the Docker image) and must be the same matches on every machine. ``tests/test_catalogue_build.py`` checks
these pins in CI (Linux) and ``python -m regista.cloud.smoke`` checks them inside the built image. A generator or
definition change that moves them re-records them here (``python -m regista.catalogue check`` lists what moved).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

CATALOGUE_PINS: dict[str, str] = {
    "cm_ewo_01_wth_skb": "f5900a355c4ea67f", "cm_ewo_01_mrw_oxr": "4aef27f4458eceac",
    "cm_ewo_02_wth_hlm": "3c2b744dd2e1df6d", "cm_ewo_02_mrw_skb": "8afe0e720c12cef3",
    "cm_ewo_03_mrw_wth": "ae7df53eecf1abbd", "cm_eu18_01_crm_skw": "625de5b2fe5c8649",
    "cm_eu18_01_plb_nht": "92cc87ad5d4dfd58", "cm_eu18_02_plb_crm": "15e385c7f82f1c7e",
    "cm_eu18_02_skw_nht": "083f6171bf8b14f3", "cm_ucm_01_mpu_nmu": "cac8977d8b3b8d4a",
    "cm_ucm_02_whc_ghc": "d0ea35254e8225d6", "cm_ucm_03_kbc_ghc": "2536e02e9226cc38",
    "cm_ucm_07_kbc_mpu": "d43ce67c8dc903c9", "cm_ucm_08_ghc_kbc": "b611df4d6ce83f97",
    "cm_ucm_08_mpu_sms": "2f53b4e5f0c13b22", "cm_ucw_01_sau_msa": "265527f9aaaa97a6",
    "cm_ucw_04_rcu_crl": "63a7944142763bbc", "cm_ucw_04_phc_msa": "17da449e6bc75611",
    "cm_ucw_07_msa_rcu": "94cc4f0bd64a44ed", "cm_ucw_09_crl_rcu": "68b5a77ab5bbb693",
    "cm_eam_01_fta_bnc": "c4aa984643b8c628", "cm_eam_02_fta_tvl": "16aca3e6a92dd419",
    "cm_eam_02_rsc_bnc": "7066fd9f91671a51", "cm_eam_03_tvl_ams": "1df2becd981c5dea",
    "cm_eam_03_rsc_fta": "b8079da13af58f5d", "cm_eu19_01_pij_sot": "49dcea559e126be1",
    "cm_eu19_01_pnr_nvc": "21688b8705bd9810", "cm_eu19_02_pnr_sot": "1ee0ae52c6b9d315",
    "cm_eu19_03_vdc_nvc": "8055b247adb90f26", "cm_eu19_03_pnr_pij": "27455e1e0a6315e2",
    "cm_gsp_01_hbg_hsb": "e6410dece8bd3097", "cm_gsp_01_mvs_vor": "bd8a7d6156ba1781",
    "cm_gsp_01_lmr_ehr": "75289fad2577f04b", "cm_gsp_02_hsb_ehr": "d0852644837f8f7e",
    "cm_gsp_02_lmr_vor": "5d92e9cf54d1feaf", "cm_gsp_03_hbg_ehr": "2f00877741f9a9d1",
    "cm_gsp_03_hsb_vor": "fb2bfdeee5e596ba", "cm_gsp_04_lmr_hbg": "32bc692716b5b378",
    "cm_bu20_01_arn_glc": "81b8553696caddb6", "cm_bu20_03_epa_glc": "cc6ad60dd5239c26",
    "cm_bu20_04_uma_epa": "a69725bf120f508c", "cm_bu20_04_glc_arn": "25d3ddaaea1389b6",
    "cm_nam_01_ads_pgr": "6dbcab79cff898ce", "cm_nam_01_irk_rbw": "5ecd6c4503af2e1e",
    "cm_nam_02_irk_ads": "e4cd52d7b3cff5ec", "cm_nam_02_pgr_rbw": "852bfdd08f851d37",
    "cm_gu17_01_ktr_rfe": "b852aee930dc2de0", "cm_gu17_01_cch_adk": "2a94f77780427258",
    "cm_gu17_02_cch_ktr": "e48559e1e0d5ef6f", "cm_jum_01_hmk_ssg": "d2b79a08365d53f3",
    "cm_jum_02_aoz_ssg": "340ecdaa6c2c5377", "cm_jum_05_kgu_hmk": "b7e2ceecb3d7119f",
    "cm_jum_05_ssg_aoz": "ee10427215f9bbbd", "cm_mam_01_ale_aga": "827c2fdfbdbcbe49",
    "cm_mam_02_utr_ale": "5bebc501ef021c8d", "cm_mam_03_ale_dbh": "85469283286feb03",
    "cm_mam_04_dbh_utr": "fe343672b0bbf897", "cm_mu19_01_ioz_cjv": "8e6fbd2d8aa509bf",
    "cm_mu19_01_ncj_naj": "e36a4d2199bbcee2", "cm_mu19_02_ncj_ioz": "a236cf87366fa539",
}


def drift(comps: list[dict[str, Any]] | None = None, root: Path | str | None = None) -> dict[str, str]:
    """{match_id: what this machine built} for every catalogue match whose built ``events.jsonl`` differs from its pin
    (missing folders and unpinned matches included). Empty when the catalogue here is the committed one, bit for bit."""
    from regista.catalogue import store

    comps = store.new_competitions() if comps is None else comps
    root = Path(root) if root is not None else store.matches_root()
    out = {}
    for comp in comps:
        for fx in comp["fixtures"]:
            path = root / fx["match_id"] / "events.jsonl"
            got = hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "missing"
            if got != CATALOGUE_PINS.get(fx["match_id"]):
                out[fx["match_id"]] = got
    return out
