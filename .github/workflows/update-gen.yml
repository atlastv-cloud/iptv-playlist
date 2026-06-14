name: Update GEN Stream

on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v3

      - name: Install Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install playwright
          playwright install

      - name: Run updater
        run: python update_gen.py

      - name: Commit changes
        run: |
          git config --global user.name "github-actions"
          git config --global user.email "actions@github.com"
          git add AtlasTVPilar.m3u
          git diff --quiet && git diff --staged --quiet || git commit -m "Auto update GEN stream"
          git push
