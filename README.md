# Office Gym Locator

This script processes `workspace_office_locations.csv` and uses the Google Gemini API to find the closest PureGym and The Gym Group locations for each office.

## Setup

1. Add your Gemini API key to the `.env` file:
   ```
   GEMINI_API_KEY=your_actual_key_here
   ```

2. Run the script:
   ```bash
   python find_gyms.py
   ```

## Output

- `puregym_locations.csv`: Closest PureGym locations.
- `gymgroup_locations.csv`: Closest The Gym Group locations.

## Review Enrichment

To generate Google Maps-grounded review coverage for each Workspace office, run:

```bash
python build_workspace_reviews.py
```

This writes `workspace_office_reviews.csv`, which powers the Streamlit page in `pages/1_Workspace_Reviews.py`.
