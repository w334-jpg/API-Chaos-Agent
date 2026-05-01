"""Batch fix test files for TestResult.summary -> TestResult.total_scenarios."""
import os, re

for root, dirs, files in os.walk('tests'):
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r') as f:
            content = f.read()
        original = content
        
        # Fix TestResult.summary.total_scenarios -> TestResult.total_scenarios
        # These are execution results, not reports
        content = content.replace('retrieved.summary.total_scenarios', 'retrieved.total_scenarios')
        
        # Fix PipelineRun.summary.failed -> PipelineRun.vulnerabilities_found
        content = content.replace('completed.summary.failed == 3', 'completed.vulnerabilities_found == 3')
        
        if content != original:
            with open(fpath, 'w') as f:
                f.write(content)
            print(f'Updated: {fpath}')
print('Done')
