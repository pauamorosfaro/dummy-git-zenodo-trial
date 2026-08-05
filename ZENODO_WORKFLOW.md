# GitHub–Zenodo Sandbox release checklist

For each new version:

1. Update `data/dummy_number_sequences.csv` in GitHub.
2. Update `CHANGELOG.md`.
3. Commit the changes.
4. Create a GitHub Release with a matching tag, for example `v0.3.0`.
5. In the Zenodo Sandbox record, click **New version**.
6. Replace the previous CSV with the exact released CSV.
7. Set the Zenodo version to `0.3.0`.
8. Add a short version note matching the changelog.
9. Preview and publish.
10. Check that GitHub and Zenodo contain the same CSV.
