"""Batch fix test files for new Report model."""
import os

replacements = [
    ('report.total_scenarios', 'report.summary.total_scenarios'),
    ('retrieved.total_scenarios', 'retrieved.summary.total_scenarios'),
    ('completed.total_scenarios', 'completed.summary.total_scenarios'),
    ('report_data["total_scenarios"]', 'report_data["summary"]["total_scenarios"]'),
    ('"severity_summary"', '"severity_counts"'),
]

for root, dirs, files in os.walk('tests'):
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r') as f:
            content = f.read()
        original = content
        for old, new in replacements:
            content = content.replace(old, new)
        if content != original:
            with open(fpath, 'w') as f:
                f.write(content)
            print(f'Updated: {fpath}')
print('Done')
