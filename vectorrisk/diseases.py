"""Vector-borne disease / vector-species reference data (Africa-focused).

Scientifically reviewed and corrected relative to common compilations:
  * Symbionts are stated accurately per vector genus. Wolbachia is NOT a natural
    symbiont of Aedes aegypti or Anopheles; it is *introduced* into Aedes for
    biocontrol. Anopheles has the naturally occurring transmission-blocking
    symbiont Microsporidia MB. Tsetse carry Wigglesworthia/Sodalis. For ticks,
    Borrelia is the PATHOGEN, not a symbiont.
  * Arbovirus vectors include Aedes albopictus and sylvatic Aedes, not only
    Ae. aegypti. Rift Valley fever uses both Aedes and Culex.
  * Non-African diseases (Lyme, TBE, tularemia) are flagged so the Africa
    platform can hide them by default.

Each disease also carries a ``thermal_group`` (Anopheles/Aedes/Culex/Sandfly/
Tsetse/Tick) and ``model_applicability``: the abundance model is currently
calibrated for *Anopheles*. Other groups have different thermal optima and need
re-parameterisation before their risk maps are quantitatively valid -- this is
surfaced so users are not misled.
"""
from __future__ import annotations

from typing import Dict

# Thermal-biology groups -> notes + (future) parameter overrides for the model.
VECTOR_GROUPS: Dict[str, dict] = {
    "Anopheles": {"symbiont": "Microsporidia MB (natural, transmission-blocking)",
                  "thermal_note": "Model calibrated for Anopheles (T-opt ~25-27C).",
                  "model_ready": True},
    "Aedes": {"symbiont": "Wolbachia (introduced for biocontrol; not native)",
              "thermal_note": "Warmer optimum (~29C) and container breeding; re-parameterise.",
              "model_ready": False},
    "Culex": {"symbiont": "Wolbachia (naturally present in Culex pipiens complex)",
              "thermal_note": "Tolerates organically enriched water; re-parameterise.",
              "model_ready": False},
    "Sandfly": {"symbiont": "None established (Wolbachia reported in some populations)",
                "thermal_note": "Phlebotomine biology differs; not an abundance-model target yet.",
                "model_ready": False},
    "Tsetse": {"symbiont": "Wigglesworthia glossinidia; Sodalis glossinidius; Wolbachia",
               "thermal_note": "Larviparous, single larva; distinct dynamics; re-parameterise.",
               "model_ready": False},
    "Tick": {"symbiont": "Endosymbionts (Coxiella-like, Rickettsia); NB Borrelia is the pathogen",
             "thermal_note": "Multi-host, humidity-driven; not a mosquito-abundance target.",
             "model_ready": False},
}


def _d(vector, group, species, distribution, habitat, pathogen, treatment,
       african, significance="", behavior=""):
    return dict(vector=vector, thermal_group=group, species=species,
                distribution=distribution, habitat=habitat, pathogen=pathogen,
                treatment=treatment, african=african, significance=significance,
                behavior=behavior,
                symbiont=VECTOR_GROUPS[group]["symbiont"],
                thermal_note=VECTOR_GROUPS[group]["thermal_note"],
                model_applicability=("direct - model calibrated for this vector"
                                     if VECTOR_GROUPS[group]["model_ready"]
                                     else "indicative only - needs re-parameterisation for this vector"))


DISEASES: Dict[str, dict] = {
    "Malaria": _d(
        "Anopheles mosquito", "Anopheles",
        ["Anopheles gambiae", "Anopheles coluzzii", "Anopheles funestus",
         "Anopheles arabiensis", "Anopheles stephensi"],
        "Sub-Saharan Africa, South Asia, Middle East",
        "Freshwater marshes, rice fields, temporary rain pools, increasingly urban",
        ["Plasmodium falciparum", "Plasmodium vivax", "Plasmodium ovale",
         "Plasmodium malariae", "Plasmodium knowlesi"],
        ["Artemisinin-based combination therapies (ACTs)", "chloroquine (where sensitive)"],
        True, "Primary malaria vectors; An. stephensi an emerging urban invader in the Horn of Africa.",
        "Mainly anthropophilic, night-biting"),
    "Dengue": _d(
        "Aedes mosquito", "Aedes", ["Aedes aegypti", "Aedes albopictus"],
        "Tropics and subtropics worldwide; expanding in African cities",
        "Urban areas, water-storage containers, discarded tyres",
        ["Dengue virus (DENV 1-4)"],
        ["Supportive care (fluids, paracetamol; avoid NSAIDs)"],
        True, "Day-biting; urban arbovirus of growing concern in Africa.",
        "Anthropophilic, day-biting"),
    "Zika Fever": _d(
        "Aedes mosquito", "Aedes", ["Aedes aegypti", "Aedes albopictus"],
        "Tropics and subtropics; documented African transmission",
        "Urban containers with standing water",
        ["Zika virus"], ["Supportive care", "prevention in pregnancy (congenital risk)"],
        True, "Sexual and vertical transmission also occur.", "Anthropophilic, day-biting"),
    "Yellow Fever": _d(
        "Aedes mosquito", "Aedes",
        ["Aedes aegypti", "Aedes albopictus", "Aedes africanus (sylvatic)"],
        "Sub-Saharan Africa and tropical South America",
        "Urban containers (urban cycle) and forest canopy (sylvatic cycle)",
        ["Yellow fever virus"], ["Supportive care", "highly effective YF vaccine (EPI)"],
        True, "Endemic across the African YF belt; vaccine-preventable.",
        "Urban and sylvatic cycles"),
    "Chikungunya": _d(
        "Aedes mosquito", "Aedes", ["Aedes aegypti", "Aedes albopictus"],
        "Tropics and subtropics; recurrent African outbreaks",
        "Urban containers with standing water",
        ["Chikungunya virus (CHIKV)"], ["Supportive care (analgesia, fluids)"],
        True, "Debilitating arthralgia; Ae. albopictus drives some outbreaks.",
        "Anthropophilic, day-biting"),
    "West Nile Fever": _d(
        "Culex mosquito", "Culex", ["Culex pipiens", "Culex quinquefasciatus"],
        "Worldwide including Africa",
        "Stagnant/organically enriched water, urban and peri-urban",
        ["West Nile virus"], ["Supportive care"],
        True, "Bird-amplified; humans are dead-end hosts.", "Zoophilic and anthropophilic"),
    "Rift Valley Fever": _d(
        "Aedes & Culex mosquitoes", "Culex",
        ["Aedes mcintoshi", "Aedes vexans", "Culex pipiens", "Culex quinquefasciatus"],
        "Africa and the Arabian Peninsula",
        "Flood-water dambos (Aedes) and irrigation (Culex); livestock areas",
        ["Rift Valley fever virus (RVFV)"], ["Supportive care", "livestock vaccination/control"],
        True, "Epizootic-linked; Aedes give transovarial maintenance, Culex amplify.",
        "Zoophilic and anthropophilic"),
    "Leishmaniasis": _d(
        "Phlebotomine sandfly", "Sandfly", ["Phlebotomus spp.", "(New World: Lutzomyia spp.)"],
        "East Africa, North/Sub-Saharan foci, Mediterranean, South Asia, Americas",
        "Rodent burrows, cracks, forests; peri-domestic",
        ["Leishmania donovani (visceral)", "Leishmania spp. (cutaneous)"],
        ["Liposomal amphotericin B", "antimonials", "miltefosine"],
        True, "Visceral leishmaniasis (kala-azar) endemic in East Africa.",
        "Anthropophilic and zoophilic, night-biting"),
    "African Trypanosomiasis": _d(
        "Glossina tsetse fly", "Tsetse", ["Glossina morsitans", "Glossina palpalis"],
        "Sub-Saharan Africa (tsetse belt)",
        "Riverine forests (palpalis) and savanna woodland (morsitans)",
        ["Trypanosoma brucei gambiense", "Trypanosoma brucei rhodesiense"],
        ["Fexinidazole (oral)", "pentamidine", "NECT (nifurtimox-eflornithine)"],
        True, "Sleeping sickness; also animal trypanosomiasis (nagana).",
        "Both sexes bite; day-active"),
    "Crimean-Congo Haemorrhagic Fever": _d(
        "Hyalomma tick", "Tick", ["Hyalomma marginatum", "Hyalomma rufipes"],
        "Africa, Asia, southern/eastern Europe",
        "Arid and semi-arid rangeland; livestock",
        ["Crimean-Congo haemorrhagic fever virus (CCHFV)"],
        ["Ribavirin (debated)", "supportive/intensive care"],
        True, "Livestock- and nosocomial-linked; high case-fatality.",
        "Zoophilic and anthropophilic"),
    # --- Non-African (kept for completeness; hidden by default in the app) ---
    "Lyme Disease": _d(
        "Ixodes tick", "Tick", ["Ixodes scapularis", "Ixodes pacificus", "Ixodes ricinus"],
        "North America, Europe, temperate Asia (not endemic in most of Africa)",
        "Deciduous forests, grasslands, leaf litter",
        ["Borrelia burgdorferi (s.l.)"], ["Doxycycline", "amoxicillin", "ceftriaxone"],
        False, "Borrelia is the pathogen, not a symbiont.", "Zoophilic and anthropophilic"),
    "Tick-borne Encephalitis": _d(
        "Ixodes tick", "Tick", ["Ixodes ricinus", "Ixodes persulcatus"],
        "Europe and northern Asia (not African)",
        "Forests and forest-edge grasslands",
        ["Tick-borne encephalitis virus (TBEV)"], ["Supportive care", "TBE vaccine"],
        False, "Vaccine-preventable; not an African disease.", "Zoophilic and anthropophilic"),
    "Tularemia": _d(
        "Tick / deer fly", "Tick",
        ["Amblyomma americanum", "Dermacentor variabilis"],
        "North America, Europe, Asia (not African)",
        "Forests, grasslands, wetlands",
        ["Francisella tularensis"], ["Streptomycin", "gentamicin", "doxycycline"],
        False, "Multiple non-vector routes (aerosol, contact).", "Zoophilic and anthropophilic"),
}


def list_diseases(african_only: bool = True):
    return {name: {"vector": d["vector"], "thermal_group": d["thermal_group"],
                   "african": d["african"], "model_applicability": d["model_applicability"],
                   "pathogen": d["pathogen"]}
            for name, d in DISEASES.items() if (d["african"] or not african_only)}
