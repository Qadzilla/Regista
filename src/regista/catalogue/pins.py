"""The catalogue's matches, pinned: the first 16 hex digits of each catalogue match's ``events.jsonl`` as
``regista.catalogue.build`` writes it, recorded on macOS (arm64, Python 3.13) with generator 0.7.1. The five Spain U19 pins were re-recorded in review round 1:
the competition was renamed (Liga Juvenil Levante Interior, Valencian Community) and its name is in each match's header;
nothing else in those streams moved.

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
    "cm_ewo_01_mrw_oxr": "89505560e914d129", "cm_ewo_03_mrw_wth": "fa70673fc37c0224",
    "cm_ewo_05_hlm_skb": "6ae8cc556a7d64e4", "cm_ewo_05_oxr_wth": "e1451d9a170522bb",
    "cm_ewo_10_skb_hlm": "22d3125002ca57b4", "cm_eu18_01_crm_skw": "625de5b2fe5c8649",
    "cm_eu18_03_skw_plb": "00889102bd1d3ecf", "cm_eu18_04_nht_plb": "068f6aa61b378f69",
    "cm_eu18_06_plb_skw": "806cf3563a7b9be4", "cm_ucm_01_mpu_nmu": "cac8977d8b3b8d4a",
    "cm_ucm_02_whc_ghc": "d0ea35254e8225d6", "cm_ucm_03_kbc_ghc": "2536e02e9226cc38",
    "cm_ucm_07_kbc_mpu": "d43ce67c8dc903c9", "cm_ucm_08_ghc_kbc": "b611df4d6ce83f97",
    "cm_ucm_08_mpu_sms": "2f53b4e5f0c13b22", "cm_ucw_01_sau_msa": "265527f9aaaa97a6",
    "cm_ucw_04_rcu_crl": "63a7944142763bbc", "cm_ucw_04_phc_msa": "17da449e6bc75611",
    "cm_ucw_07_msa_rcu": "94cc4f0bd64a44ed", "cm_ucw_09_crl_rcu": "68b5a77ab5bbb693",
    "cm_eam_03_tvl_ams": "82dd690110fd66d2", "cm_eam_04_rsc_tvl": "a3de27de282370a5",
    "cm_eam_05_ams_fta": "28ad4677f11c1a09", "cm_eam_06_bnc_fta": "69f24124a700380f",
    "cm_eam_10_fta_ams": "62189fd91faa3e10", "cm_eu19_01_pij_sot": "49dcea559e126be1",
    "cm_eu19_05_vdc_sot": "7c687dcd179e951a", "cm_eu19_06_nvc_pnr": "14d231c62b039588",
    "cm_eu19_07_vdc_pij": "e4c3328c097c6292", "cm_eu19_10_pij_nvc": "00010f0f7f0dbb80",
    "cm_gsp_01_hbg_hsb": "e6410dece8bd3097", "cm_gsp_01_mvs_vor": "bd8a7d6156ba1781",
    "cm_gsp_01_lmr_ehr": "75289fad2577f04b", "cm_gsp_02_hsb_ehr": "0d39b7921d773302",
    "cm_gsp_04_lmr_hbg": "61c9b627b3d652cc", "cm_gsp_05_hsb_lmr": "19c1bf1901f7209e",
    "cm_gsp_06_ehr_lmr": "1cdcdd4baa021823", "cm_gsp_07_hbg_mvs": "0ec2e060a0151751",
    "cm_bu20_01_arn_glc": "81b8553696caddb6", "cm_bu20_03_epa_glc": "cc6ad60dd5239c26",
    "cm_bu20_05_glc_uma": "1f40c052a0d106de", "cm_bu20_06_glc_epa": "895442f27e619821",
    "cm_nam_02_irk_ads": "789cd7302f82a7a9", "cm_nam_03_ads_rbw": "ac51749b0e49d6bf",
    "cm_nam_04_rbw_irk": "fb32cebd405a2d5f", "cm_nam_05_rbw_pgr": "ce682b70b9515a72",
    "cm_gu17_02_cch_ktr": "1f976121ea6a9114", "cm_gu17_05_adk_rfe": "4f708add2e0a1263",
    "cm_gu17_06_adk_ktr": "e699f83188c7c773", "cm_jum_01_hmk_ssg": "d2b79a08365d53f3",
    "cm_jum_02_aoz_ssg": "340ecdaa6c2c5377", "cm_jum_05_kgu_hmk": "b7e2ceecb3d7119f",
    "cm_jum_05_ssg_aoz": "ee10427215f9bbbd", "cm_mam_03_ale_dbh": "04761e9b7a78b479",
    "cm_mam_03_aga_utr": "d7cbeb26ebadfe09", "cm_mam_05_dbh_aga": "ef7bbda3e7c36f7f",
    "cm_mam_06_dbh_ale": "e66549c1cec421f7", "cm_mu19_01_ncj_naj": "650fb0f2da52d86b",
    "cm_mu19_05_ioz_ncj": "3f901411f14a1951", "cm_mu19_06_ncj_cjv": "25a0b0fe4576a6eb",
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
