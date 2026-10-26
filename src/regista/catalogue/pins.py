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
    "cm_ewo_01_wth_skb": "39fb7cee37d8b6d6", "cm_ewo_01_mrw_oxr": "0e89ef738da2b4a6",
    "cm_ewo_02_wth_hlm": "b507b7e344a0450d", "cm_ewo_02_mrw_skb": "5b34e555ebe51b8f",
    "cm_ewo_03_mrw_wth": "f4166b50ca96bd8a", "cm_eu18_01_crm_skw": "1cdac0ff078c2222",
    "cm_eu18_01_plb_nht": "e46ec802833afe9a", "cm_eu18_02_plb_crm": "74a561e1cb2468b4",
    "cm_eu18_02_skw_nht": "6e92b852836ef89e", "cm_ucm_01_mpu_nmu": "6ba9a7b1dd9bb0c1",
    "cm_ucm_02_whc_ghc": "485b81dd19cb6a3e", "cm_ucm_03_kbc_ghc": "f3ec6e0e11a8ff99",
    "cm_ucm_07_kbc_mpu": "674fad2b66a07a29", "cm_ucm_08_ghc_kbc": "984e9db274b336ab",
    "cm_ucm_08_mpu_sms": "391bc1ab6e785581", "cm_ucw_01_sau_msa": "2c056e5424e04177",
    "cm_ucw_04_rcu_crl": "1b351bde2bfbc75c", "cm_ucw_04_phc_msa": "74cbf9cebd1eb656",
    "cm_ucw_07_msa_rcu": "289176a5d09cddd4", "cm_ucw_09_crl_rcu": "a120ecf9605f8a49",
    "cm_eam_01_fta_bnc": "8594832d36aeb35e", "cm_eam_02_fta_tvl": "071bc3bd4f176b74",
    "cm_eam_02_rsc_bnc": "f6d811e655ab931c", "cm_eam_03_tvl_ams": "036413ae3bdcbb58",
    "cm_eam_03_rsc_fta": "f80a55330b57c4d0", "cm_eu19_01_pij_sot": "9defc2d78f45ae77",
    "cm_eu19_01_pnr_nvc": "11412337d8835a4a", "cm_eu19_02_pnr_sot": "f08906454ca163b8",
    "cm_eu19_03_vdc_nvc": "c93b3da26a4e3ab0", "cm_eu19_03_pnr_pij": "0046c203f84d507c",
    "cm_gsp_01_hbg_hsb": "e6410dece8bd3097", "cm_gsp_01_mvs_vor": "bd8a7d6156ba1781",
    "cm_gsp_01_lmr_ehr": "75289fad2577f04b", "cm_gsp_02_hsb_ehr": "d0852644837f8f7e",
    "cm_gsp_02_lmr_vor": "5d92e9cf54d1feaf", "cm_gsp_03_hbg_ehr": "2f00877741f9a9d1",
    "cm_gsp_03_hsb_vor": "fb2bfdeee5e596ba", "cm_gsp_04_lmr_hbg": "32bc692716b5b378",
    "cm_bu20_01_arn_glc": "7df847153fe0be0c", "cm_bu20_03_epa_glc": "6445605e63b04d98",
    "cm_bu20_04_uma_epa": "5b67c510ef8e4f23", "cm_bu20_04_glc_arn": "b1c935c8bdd8545e",
    "cm_nam_01_ads_pgr": "5a41ed63baec7a70", "cm_nam_01_irk_rbw": "bb7ad388a4f8363f",
    "cm_nam_02_irk_ads": "f49d0d33ac67872a", "cm_nam_02_pgr_rbw": "c217389e570f19af",
    "cm_gu17_01_ktr_rfe": "cfd73f62ea665a13", "cm_gu17_01_cch_adk": "2c6853acad0995ab",
    "cm_gu17_02_cch_ktr": "3395ad270f74163b", "cm_jum_01_hmk_ssg": "7797d0497818abc6",
    "cm_jum_02_aoz_ssg": "4e245d2988ce779d", "cm_jum_05_kgu_hmk": "84aa3cb3a09c1ef7",
    "cm_jum_05_ssg_aoz": "a592cfb0ff4d870d", "cm_mam_01_ale_aga": "fb524cc2b39e9b8a",
    "cm_mam_02_utr_ale": "c1709e65408bcdc0", "cm_mam_03_ale_dbh": "1086fc19bbb9f0b9",
    "cm_mam_04_dbh_utr": "9f20432df445e789", "cm_mu19_01_ioz_cjv": "ed8958d93b4467f6",
    "cm_mu19_01_ncj_naj": "f6ccbb712ef4fd8e", "cm_mu19_02_ncj_ioz": "f3fc00da7ca1e752",
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
