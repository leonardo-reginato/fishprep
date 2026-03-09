# fishprep

`fishprep` scans mixed-format fish image datasets, converts them to standardized JPEGs, detects duplicates, scores image quality, and organizes the results into `standard`, `duplicates`, and `low_quality` folders.

## Install

```bash
pip install -r requirements.txt
```

Optional:

```bash
pip install rawpy
```

`rawpy` enables DNG conversion. Without it, DNG files are cataloged but conversion will fail with a clear error.

## How To Use

1. Install the dependencies.

```bash
pip install -r requirements.txt
```

2. Edit `config.yml` and set the input dataset folder and output folder.

Example `config.yml`:

```yaml
dataset_dir: /path/to/raw_dataset
output_dir: /path/to/output_dataset
jpeg_quality: 90
max_size_mb: 10
duplicate_tolerance: 5
blur_threshold: 5
use_prefix_before_second_underscore: false
enable_centering_check: false
centering_threshold: 0.2
```

3. Run the pipeline.

```bash
python run.py --config config.yml
```

4. Check the generated CSV files in the output directory.

## GUI Review

If you want to run the automatic analysis first and then review duplicate groups in a desktop interface, use:

```bash
python gui_run.py
```

The GUI will:

- let you set analysis inputs directly in the `Settings` tab without editing `config.yml`
- run the same automatic pipeline
- load `duplicate_groups.csv` after the analysis finishes
- show near-duplicate review groups with a reference image and the related candidates
- auto-resolve exact duplicates and send only tolerance-based similar groups to review
- let you change which image is the group reference
- let you mark each reviewed candidate as `keep`, `exclude`, or `unsure`
- save those manual decisions to `duplicate_review_decisions.csv`
- write the reviewed `catalog.csv`
- create the final `standard`, `duplicates`, and `low_quality` folders when you click `Save and Finish`

## GUI Settings

The `Settings` tab includes:

- `Dataset directory`: folder containing the original images to scan
- `Output directory`: folder where reports, logs, and final outputs will be written
- `JPEG quality`: output JPEG quality used during final conversion; higher values keep more detail and larger files
- `Max size (MB)`: maximum allowed size for each final JPEG output
- `Duplicate tolerance`: perceptual-hash distance used to flag near-duplicate images for manual review
- `Blur threshold`: threshold used to mark blurry images as low quality
- `Use first two underscore groups for output names`: when enabled, filenames like `XPTO26_22_Genus_species_ID3813.png` are saved as `XPTO26_22.jpg`; unformatted names fall back to the normal naming logic
- `Enable centering check`: toggles the off-center quality filter
- `Centering threshold`: sensitivity for the centering check when enabled

Guidance for `Duplicate tolerance`:

- `0-3`: very strict, mostly catches only near-identical images
- `4-6`: balanced, good default range for resized or lightly changed copies
- `7-9`: loose, more likely to group sequence shots or slightly different frames
- `10+`: aggressive, higher chance of false positives

In practice, `7` is moderately high. It is useful if you want to review images taken in sequence that look very similar, but it may group more images than you really want.

## Review Actions

The `Review` tab shows one near-duplicate group at a time:

- the `Reference Image` is the current representative image for that group, usually the best-quality one chosen automatically
- the `Selected Candidate` is the image currently highlighted in the `Candidates` table
- exact duplicates are not shown here; they are resolved automatically

The review buttons do this:

- `Keep`: keep the selected candidate as a valid image; it will go to `standard/` or `low_quality/`
- `Exclude`: mark the selected candidate as a duplicate; it will go to `duplicates/`
- `Unsure`: leave the candidate without a manual override and fall back to the automatic category
- `Keep All In Group`: apply `keep` to all duplicate candidates in the current group
- `Exclude All In Group`: apply `exclude` to all duplicate candidates in the current group
- `Set As Reference`: promote the selected candidate to be the new reference image for the group
- `Save and Finish`: write `duplicate_review_decisions.csv`, update `catalog.csv`, and create the final output folders

Manual review decisions are stored in `duplicate_review_decisions.csv` inside the selected output directory and are also logged in `summary.txt`.

## Configuration

- `dataset_dir`: folder containing the original images
- `output_dir`: folder where all outputs will be written
- `jpeg_quality`: JPEG quality used during conversion
- `max_size_mb`: maximum size allowed for converted JPEG files
- `duplicate_tolerance`: perceptual-hash tolerance used to flag near-duplicate images for manual review
- `use_prefix_before_second_underscore`: when `true`, output filenames use everything before the second `_` when the source filename is formatted that way
- `blur_threshold`: lower values make the blur filter less strict
- `enable_centering_check`: enables or disables the off-center filter
- `centering_threshold`: off-center sensitivity when `enable_centering_check` is enabled

## Example Config

```yaml
dataset_dir: /path/to/raw_dataset
output_dir: /path/to/output_dataset
jpeg_quality: 90
max_size_mb: 10
duplicate_tolerance: 5
blur_threshold: 5
use_prefix_before_second_underscore: false
enable_centering_check: false
centering_threshold: 0.2
```

## Outputs

- `catalog.csv`: single final catalog containing the original path, final organized path, hashes, quality metrics, duplicate flags, and low-quality flags
- `duplicate_groups.csv`: near-duplicate review table with reference images and candidate images that fall within the duplicate tolerance
- `duplicate_review_decisions.csv`: manual GUI decisions for duplicate review
- `summary.txt`: run log with configuration settings, analysis stages, review decisions, final counts, and completion message
- `standard/`: converted JPEGs kept as standard images
- `duplicates/`: converted JPEGs flagged as duplicates
- `low_quality/`: converted JPEGs flagged as blurry or off-center

## Notes

- Original files are not modified.
- The GUI analyzes original files directly and only converts images when final output files are written.
- Exact duplicates are handled automatically and are named from their reference image with `_dup`, `_dup01`, `_dup02`, and so on.
- Similar-but-not-exact images are only moved to `duplicates/` when you exclude them during review; their names are derived from the selected group reference with `_01`, `_02`, `_03`, and so on.
- Standard and low-quality images keep their original base filename. Only duplicate-related images receive suffixes.
- When `use_prefix_before_second_underscore` is enabled, formatted filenames keep only the first two underscore-separated parts before duplicate suffixes are applied.
- When `use_prefix_before_second_underscore` is enabled, repeated formatted prefixes such as `XPTO25_01` are also used to auto-group same-individual images, choose the best-quality reference, and assign duplicate suffixes without sending those images to manual review first.
- If `rawpy` is not installed, DNG files may be scanned but will not convert successfully.
