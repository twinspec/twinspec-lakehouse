# TwinSpec Lakehouse

TwinSpec is a small, local-first data lakehouse for building a GIWAXS-focused digital twin.

This repository stores:

- **Literature data** (papers, GIWAXS/XRD figures, digitized CSVs)
- **Computed data** (geometry for films, RDKit descriptors, etc.)
- **Curated tables** (materials, experiments, computed structures, descriptors)
- **ML-ready features** (for synthetic data and model training)
- **Utility scripts** (digitization helpers, path audits, Unity metadata export)

The lakehouse is designed to be simple enough for a laptop workflow and easy to mirror to cloud object storage later.

---

## Directory structure

```text
twinspec-lakehouse/
  raw/
    computed/
      geometry_xyz/        # XYZ, PDB, CIF-derived geometries for films/slabs
      rdkit_descriptors/   # Optional raw RDKit/other descriptor dumps
    literature/
      giwaxs_1d/           # Standardized 1D linecut CSVs (q vs intensity)
      giwaxs_2d/           # Standardized 2D GIWAXS/XRD maps (qz, qxy, intensity)
      papers/              # Source PDFs from literature
      method_json/         # Per-paper experimental metadata JSON (optional)
      fig_crops/           # (Optional) Cropped figure images used for digitization

  curated/
    materials/
      materials.csv        # One row per material (polymer, oxide, MOF, biomaterial, etc.)
      materials_example_use
    experiments/
      experiments.csv      # One row per film/experiment; links to digitized GIWAXS paths
      experiments_example_use
    computed_structures/
      computed_structures.csv      # One row per geometry asset (film/slab/segment)
      computed_structures_example_use
    descriptors/
      descriptors.csv              # Per-material descriptors (e.g. RDKit) in JSON
      descriptors_example_use

  feature_store/
    ml_ready/
      features_unified.csv         # Joined, ML-ready feature rows (material + experiment + structure)
      features_unified_example_use

  scripts/
    digitize_giwaxs.py             # Standardize raw digitized CSVs into TwinSpec 1D/2D formats
    audit_paths.py                 # Check that paths in curated CSVs actually exist
    generate_unity_metadata.py     # Export Unity metadata JSON for flagged experiments

  unity_metadata/                  # Auto-generated metadata JSON files for Unity (output of generate_unity_metadata.py)

  docs/
    lakehouse_overview.md
    paper_extraction_checklist.txt

  README.md
  .gitignore
```

## Core CSV tables

`
curated/materials/materials.csv
`


One row per material.
        
```csv
| material_id | class | name | subclass | chemical_formula | repeat_unit_smiles | notes |
|-------------|-------|------|----------|------------------|--------------------|-------|
```

Example:
    
```csv
| material_id   |  class  |     name     |      subclass      | chemical_formula | repeat_unit_smiles |            notes                   |
|---------------|---------|--------------|--------------------|------------------|--------------------|----------------------------|
| PNDI2ODT2     | polymer | P(NDI2OD-T2) | conjugated_polymer |                  |     SMILES_HERE    | DA polymer for GIWAXS demo                    |
| PE            | polymer | Polyethylene | commodity_polymer  |      (CH2)n      |         CC         | Reference semicrystalline polymer |
| TiO2_anatase  |  oxide  | TiO2 (anatase) | metal_oxide      |                  |                    | Anatase phase for slab film                    |
```

`
curated/experiments/experiments.csv
`

One row per film / experiment extracted from literature or generated in-house.
    
```csv
|    experiment_id    | material_id | reference_type |  reference_doi    |    solvent    | concentration_mg_ml | casting_method | substrate | anneal_temp_C | anneal_time_min | film_thickness_nm | characterization_type | characterization_metadata_json | peaks_json | orientation_label | giwaxs_1d_path | giwaxs_2d_path | include_in_unity | notes |
|---------------------|-------------|----------------|-------------------|---------------|---------------------|----------------|------------|---------------|-----------------|-------------------|-----------------------|--------------------------------|------------|--------------------|----------------|----------------|------------------|-------|
```

- `characterization_type` : GIWAXS, XRD, SAXS, etc
- `characterization_metadata_json` : JSON string for beam energy, incident angle, detector, etc.
- `peaks_json` : JSON string for q-peaks, d-spacings, etc.
- `orientation_label` : e.g. `edge-on`, `face-on`, `mixed`, `textured`, `isotropic`, `unknown`
- `giwaxs_1d_path` : repo-relative path to standardized 1D CSV in `raw/literature/giwaxs_1d/`
- `giwaxs_2d_path` : repo-relative path to standardized 2D CSV in `raw/literature/giwaxs_2d/`
- `include_in_unity` : 1/true to export Unity metadata for this experiment

Example:
    
```csv
|    experiment_id    | material_id | reference_type |  reference_doi    |    solvent    | concentration_mg_ml | casting_method | substrate | anneal_temp_C | anneal_time_min | film_thickness_nm | characterization_type | characterization_metadata_json | peaks_json | orientation_label | giwaxs_1d_path | giwaxs_2d_path | include_in_unity | notes |
|---------------------|-------------|----------------|-------------------|---------------|---------------------|----------------|--------------|---------------|-----------------|-------------------|-----------------------|--------------------------------|------------|--------------------|----------------|----------------|------------------|-------|
| PNDI2ODT2_CB_120C   |  PNDI2ODT2  |   literature   | 10.1234/abcd.5678 | chlorobenzene |        10           |    bladecoat   |     SiO2      |      120      |        10       |        85         |         GIWAXS        |  "{""beam_energy_keV"":10.0}"  | "{""q100"":0.30,""q001"":1.76,""d100"":20.9,""d001"":3.57}" | "edge-on" | "Main demo film" | raw/literature/giwaxs_1d/PNDI2ODT2_CB_120C_linecut.csv | raw/literature/giwaxs_2d/PNDI2ODT2_CB_120C_map.csv | 1 |
```

`
curated/computed_structures/computed_structures.csv
`

One row per geomtry (film segment, slab, etc.) that can be loaded into Unity or used for analysis.
    
```csv
| structure_id | material_id | reference_type | method | geometry-path | box_size_A | created_at | notes |
|--------------|-------------|----------------|--------|---------------|------------|------------|-------|
```

- `geometry_path` : repo-relative path to XYZ/PDB file in `raw/computed/geometry_xyz/`
- `box_size_A` : JSON string for box dimensions, e.g. `{"Lx":80, "Ly":80, "Lz":50}`


`
curated/descriptors/descriptors.csv
`

Per-material descriptors (e.g. RDKit), stored as JSON.
    
```csv
| material_id | descriptor_source | descriptor_json | created_at | notes |
|-------------|-------------------|-----------------|------------|-------|
```


Example:
    
```csv
| material_id | descriptor_source |                       descriptor_json                    | created_at | notes |
|-------------|-------------------|----------------------------------------------------------|------------|-------|
| PNDI2ODT2   | RDKit             | "{""TPSA"":150.0,""logP"":6.2,""aromatic_atoms"":34}"    | 2025-12-10 |       |
```

`
feature_store/ml_ready/features_unified.csv
`

Joined feature rows (material + experiment + structure) for ML or synthetic model input.
    
```csv
| row_id  | material_id  | experiment_id  | structure_id  | reference_type  | solvent | anneal_temp_C  | film_thickness_nm  | orientation_label | notes |
|---------|--------------|----------------|---------------|-----------------|---------|----------------|--------------------|--------------------------|-------|
```


## Scripts

`
digitize_giwaxs.py
`

Helper for standardizing raw CSV exports from WebPlotDigitizer/Engauge.

Usage (examples):
    
```bash
# 1D linecut
python scripts/digitize_giwaxs.py 1d \
--raw /path/to/WebPlotDigitizer_export.csv \
--experiment-id PNDI2ODT2_CB_120C \
--linecut-id oop \
--direction out_of_plane \
--q-units 1/A

# 2D map
python scripts/digitize_giwaxs.py 2d \
--raw /path/to/map_export.csv \
--experiment-id PNDI2ODT2_CB_120C \
--map-id full \
--geometry qz_qxy
```

Output paths (relative to repo root) are printed and should be pasted into `giwaxs_1d_path` / `giwaxs_2d_path` in `experiments.csv`.

## Typical Workflow (per paper)

1. Drop PDF --> `raw/literature/papers/`.
2. Crop GIWAXS/XRD figures --> `raw/literature/fig_crops/` (optional).
3. Digitize 1D/2D plots --> export raw CSV.
4. Run `digitize_giwas.py` to standardize --> files land in `raw/literature/giwaxs_1d/` or `giwaxs_2d/`.
5. Create/Update row in `curated/experiments/experiments.csv`.
6. (Optional) Add/Update `computed_structures.csv` entries for matching geometries.
7. Run `audit_paths.py` to check integrity.
8. When ready to visualize in Unity, mark `include_in_unity = 1` and run `generate_unity_metadata.py`


## Notes
- The repository is intentionally local-first; it can later be mirrored to S3 or another object store without changing the layout.
- JSON fields in CSVs (char_metadata_json, peaks_json, descriptor_json, box_size_A) should be valid JSON strings.
- All paths in CSVs are repo-relative, so cloning the repo preserves portability across machines.