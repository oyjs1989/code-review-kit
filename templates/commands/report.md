---
description: Generate formatted report from review results
---

## User Input

```text
$ARGUMENTS
```

## Supported Formats

### Markdown (default)
Human-readable format for documentation and sharing.

### HTML
Interactive web report with:
- Issue filtering
- Code highlighting
- Severity sorting
- Export options

### JSON
Machine-readable format for CI/CD integration.

## Report Sections

### 1. Executive Summary
- Total issues by severity
- Issues by category
- Trend comparison (if history available)

### 2. Critical Issues (P0)
Detailed breakdown of must-fix issues.

### 3. Important Issues (P1)
Detailed breakdown of should-fix issues.

### 4. Suggested Improvements (P2)
Detailed breakdown of nice-to-have fixes.

### 5. Metrics
- Code quality score
- Technical debt estimate
- Trend analysis

### 6. Appendix
- Rule definitions used
- Configuration applied
- Tool versions

## HTML Report Features

```html
<!-- Interactive features -->
<script>
// Issue filtering
// Severity toggle
// Category filter
// Search functionality
// Export to PDF/Markdown
</script>
```

## CI/CD Integration

For CI/CD pipelines, generate exit code:
- Exit 0: No P0/P1 issues
- Exit 1: P0 issues found
- Exit 2: P1 issues found (configurable)
