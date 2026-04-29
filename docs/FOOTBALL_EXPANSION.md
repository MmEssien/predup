# Football Expansion Summary

## Final Production Configuration

### Production Leagues (Confirmed Positive ROI)
| League | DB ID | API ID | Threshold | Samples | ROI | Volume |
|--------|-------|--------|-----------|---------|-----|--------|
| **BL1** | 7 | 78 | 0.70 | 611 | +12.9% | 82 bets |
| **PL** | 3 | 39 | 0.50 | 760 | +6.5% | 156 bets |

### Testing League (Promising, needs more validation)
| League | DB ID | API ID | Threshold | Samples | ROI | Volume |
|--------|-------|--------|-----------|---------|-----|--------|
| PD | 12 | 140 | 0.35 | 760 | +4.5% | 155 bets |

### Paused Leagues
| League | Status | Reason |
|--------|--------|--------|
| SA | Paused | Unstable results across data splits (-22.9% to +34.7%) |
| FL1 | Paused | Unstable results, negative ROI in final test |
| ELC | No Data | target_over_25 not available |
| ECD | No Data | target_over_25 not available |
| POR | No Data | target_over_25 not available |
| BSA | No Data | target_over_25 not available |

## Key Finding
SA and FL1 showed positive ROI in single configuration tests but were unstable across different train/test splits, indicating overfitting risk. They are paused until more robust validation can be performed.

## Validation Notes
- Realistic odds used for all ROI calculations
- BL1 is the strongest performer at +12.9% ROI
- PL is consistent with +6.5% ROI across splits
- PD shows promise but at very low threshold (0.35), needs review

## API-Football League IDs
- Bundesliga: 78
- Premier League: 39
- Serie A: 135
- La Liga: 140
- Ligue 1: 61
- Championship: 41
- Eredivisie: 88
- Primeira Liga: 94
- Brasileirao: 71