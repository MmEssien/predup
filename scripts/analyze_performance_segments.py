"""
Performance Segmentation Analysis Script

Analyzes historical predictions with segmentation:
1. League + Confidence Band Matrix
2. Odds Range Analysis  
3. Calibration Analysis
4. Loss Concentration
5. Threshold Optimization

Usage:
    python scripts/analyze_performance_segments.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import func, and_

from src.data.connection import DatabaseManager
from src.data.database import Prediction, Fixture, Competition, OddsData, ModelVersion
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
db_manager = DatabaseManager.get_instance()
db_manager.initialize()


def get_prediction_data(league_codes: list = None) -> pd.DataFrame:
    """
    Get prediction data - either from stored predictions or generate from model.
    """
    
    with db_manager.session() as session:
        # Check for existing predictions
        pred_count = session.query(Prediction).filter(
            Prediction.settled_at.isnot(None)
        ).count()
        
        print(f"     Found {pred_count} stored prediction records")
        
        if pred_count > 0:
            return get_stored_predictions(session, league_codes)
        else:
            print("     No stored predictions - generating from model for analysis...")
            return generate_from_model(session, league_codes)


def get_stored_predictions(session, league_codes: list = None) -> pd.DataFrame:
    """Get stored Prediction records"""
    
    query = session.query(
        Prediction.id,
        Prediction.fixture_id,
        Prediction.model_version_id,
        Prediction.prediction_type,
        Prediction.predicted_value,
        Prediction.probability,
        Prediction.confidence,
        Prediction.is_accepted,
        Prediction.actual_value,
        Prediction.is_correct,
        Prediction.predicted_at,
        Prediction.settled_at,
        Fixture.utc_date,
        Fixture.home_score,
        Fixture.away_score,
        Fixture.competition_id,
        Competition.code.label('competition_code'),
    ).join(
        Fixture, Prediction.fixture_id == Fixture.id
    ).join(
        Competition, Fixture.competition_id == Competition.id
    ).filter(
        Prediction.settled_at.isnot(None)
    )
    
    if league_codes:
        query = query.filter(Competition.code.in_(league_codes))
    
    results = query.all()
    
    df = pd.DataFrame([{
        'fixture_id': r.fixture_id,
        'predicted_value': r.predicted_value,
        'probability': r.probability,
        'is_accepted': r.is_accepted,
        'actual_value': r.actual_value,
        'is_correct': r.is_correct,
        'utc_date': r.utc_date,
        'home_score': r.home_score,
        'away_score': r.away_score,
        'competition_code': r.competition_code,
    } for r in results])
    
    return df


def generate_from_model(session, league_codes: list = None) -> pd.DataFrame:
    """Generate predictions using the trained model for all historical fixtures"""
    
    from src.features.repository import FeatureRepository
    from src.models.trainer import ModelTrainer
    
    # Get finished fixtures
    query = session.query(Fixture, Competition).join(
        Competition, Fixture.competition_id == Competition.id
    ).filter(
        Fixture.status == 'FINISHED',
        Fixture.home_score.isnot(None),
        Fixture.away_score.isnot(None)
    )
    
    if league_codes:
        query = query.filter(Competition.code.in_(league_codes))
    
    all_results = query.order_by(Competition.code, Fixture.utc_date).all()
    
    if not all_results:
        return pd.DataFrame()
    
    print(f"     Processing {len(all_results)} finished fixtures...")
    
    # Group by competition for model training
    comp_ids = {}
    for fixture, comp in all_results:
        if comp.id not in comp_ids:
            comp_ids[comp.id] = comp.code
    
    all_predictions = []
    
    for comp_id, comp_code in comp_ids.items():
        # Get fixtures for this competition
        comp_fixtures = [(f, c) for f, c in all_results if c.id == comp_id]
        print(f"       {comp_code}: {len(comp_fixtures)} fixtures")
        
        if len(comp_fixtures) < 50:
            continue
        
        try:
            # Train model
            features_config = config.get('features', {})
            repo = FeatureRepository(session, features_config)
            
            X, y = repo.get_training_data(
                competition_id=comp_id,
                target_column='target_over_25'
            )
            
            if len(X) < 50:
                continue
            
            model_config = config.get('model', {})
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
        except Exception as e:
            print(f"       Error training {comp_code}: {e}")
            continue
        
        # Generate predictions for fixtures
        for fixture, comp in comp_fixtures:
            try:
                features = repo.generate_and_store_features(
                    fixture.id,
                    include_targets=False
                )
                
                if features is None:
                    continue
                
                feature_names = list(X.columns)
                feature_vector = pd.DataFrame([features]).fillna(0)
                
                for col in feature_names:
                    if col not in feature_vector.columns:
                        feature_vector[col] = 0
                
                feature_vector = feature_vector[feature_names]
                
                # Predict
                prob = trainer.ensemble_proba(feature_vector)[0]
                pred = 1 if prob >= 0.5 else 0
                
                # Actual outcome (over 2.5 goals)
                total_goals = (fixture.home_score or 0) + (fixture.away_score or 0)
                actual = 1 if total_goals > 2 else 0
                
                all_predictions.append({
                    'fixture_id': fixture.id,
                    'predicted_value': pred,
                    'probability': prob,
                    'is_accepted': pred == 1,
                    'actual_value': actual,
                    'is_correct': pred == actual,
                    'utc_date': fixture.utc_date,
                    'home_score': fixture.home_score,
                    'away_score': fixture.away_score,
                    'competition_code': comp_code,
                })
                
            except Exception:
                continue
    
    df = pd.DataFrame(all_predictions)
    print(f"     Generated {len(df)} predictions for analysis")
    
    return df


def analyze_confidence_bands(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze performance by confidence band and league"""
    
    if len(df) == 0:
        return pd.DataFrame()
    
    # Confidence bands using probability
    bins = [0, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 1.0]
    labels = ['<45%', '45-50%', '50-55%', '55-60%', '60-65%', '65-70%', '70%+']
    df['conf_band'] = pd.cut(df['probability'], bins=bins, labels=labels, include_lowest=True)
    
    # For over/under analysis, treat "accepted" as "predicted over"
    results = df.groupby(['competition_code', 'conf_band']).agg({
        'fixture_id': 'count',
        'is_correct': ['sum', 'mean']
    }).reset_index()
    
    results.columns = ['League', 'Conf_Band', 'Bets', 'Wins', 'Win_Rate']
    results['Win_Rate'] = results['Win_Rate'] * 100
    
    # For simulated betting, calculate profit
    # Assume average odds of 1.90 for over
    results['Profit'] = (results['Wins'] * 0.90) - ((results['Bets'] - results['Wins']) * 1)
    results['ROI%'] = (results['Profit'] / results['Bets']) * 100
    
    return results


def analyze_odds_ranges(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze by odds ranges - requires odds data"""
    
    if 'avg_home_odds' not in df.columns:
        print("     Note: No odds data available - skipping odds range analysis")
        return pd.DataFrame()
    
    df = df[df['avg_home_odds'].notna()].copy()
    
    if len(df) == 0:
        return pd.DataFrame()
    
    bins = [0, 1.6, 1.8, 2.0, 2.2, 2.5, 5.0]
    labels = ['<1.6', '1.6-1.8', '1.8-2.0', '2.0-2.2', '2.2-2.5', '2.5+']
    df['odds_range'] = pd.cut(df['avg_home_odds'], bins=bins, labels=labels, include_lowest=True)
    
    results = df.groupby('odds_range').agg({
        'fixture_id': 'count',
        'is_correct': ['sum', 'mean']
    }).reset_index()
    
    results.columns = ['Odds_Range', 'Bets', 'Wins', 'Win_Rate']
    results['Win_Rate'] = results['Win_Rate'] * 100
    results['Profit'] = (results['Wins'] * 0.90) - ((results['Bets'] - results['Wins']) * 1)
    results['ROI%'] = (results['Profit'] / results['Bets']) * 100
    
    return results


def analyze_calibration(df: pd.DataFrame) -> pd.DataFrame:
    """Calibration analysis - probability vs actual"""
    
    if len(df) == 0:
        return pd.DataFrame()
    
    bins = [0, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 1.0]
    labels = ['<40%', '40-45%', '45-50%', '50-55%', '55-60%', '60-65%', '65-70%', '70%+']
    df['prob_band'] = pd.cut(df['probability'], bins=bins, labels=labels, include_lowest=True)
    
    results = df.groupby('prob_band').agg({
        'fixture_id': 'count',
        'is_correct': 'mean',
        'probability': 'mean'
    }).reset_index()
    
    results.columns = ['Prob_Band', 'N', 'Actual%', 'Mean_Prob']
    results['Expected%'] = results['Mean_Prob'] * 100
    results['Actual%'] = results['Actual%'] * 100
    results['Error'] = results['Actual%'] - results['Expected%']
    
    return results


def analyze_loss_concentration(df: pd.DataFrame) -> dict:
    """Where are losses concentrated?"""
    
    if len(df) == 0:
        return {}
    
    wins = df[df['is_correct'] == True]
    losses = df[df['is_correct'] == False]
    
    return {
        'total_bets': len(df),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(df) * 100 if len(df) > 0 else 0,
    }


def find_optimal_thresholds(df: pd.DataFrame) -> pd.DataFrame:
    """Find optimal threshold per league"""
    
    if len(df) == 0:
        return pd.DataFrame()
    
    results = []
    
    for league in df['competition_code'].unique():
        league_data = df[df['competition_code'] == league]
        
        best_thresh = 0.5
        best_roi = -100
        
        for thresh in np.arange(0.40, 0.75, 0.05):
            seg = league_data[league_data['probability'] >= thresh]
            
            if len(seg) < 10:
                continue
            
            wins = seg['is_correct'].sum()
            profit = (wins * 0.90) - ((len(seg) - wins) * 1)
            roi = (profit / len(seg)) * 100
            
            if roi > best_roi:
                best_roi = roi
                best_thresh = thresh
        
        results.append({
            'League': league,
            'Optimal_Threshold': f"{best_thresh:.2f}",
            'Expected_ROI': f"{best_roi:+.1f}%",
            'N_Fixtures': len(league_data)
        })
    
    return pd.DataFrame(results)


def print_table(df, title):
    """Print DataFrame nicely"""
    if df is None or len(df) == 0:
        print(f"\n{title}")
        print("  (No data)")
        return
    
    print(f"\n{title}")
    print("-" * 80)
    pd.set_option('display.width', 120)
    pd.set_option('display.max_columns', 10)
    print(df.to_string(index=False))


def main():
    print("\n" + "="*70)
    print("  PERFORMANCE SEGMENTATION ANALYSIS")
    print("="*70)
    
    # Focus on core leagues
    league_codes = ['BL1', 'PL']
    
    # Step 1: Get data
    print("\n[1/5] Loading/generating prediction data...")
    df = get_prediction_data(league_codes)
    
    if len(df) == 0:
        print("ERROR: No data available for analysis")
        return
    
    print(f"     Total predictions: {len(df)}")
    print(f"     Competitions: {df['competition_code'].unique().tolist()}")
    
    # Step 2: Confidence band analysis
    print("\n[2/5] Analyzing confidence bands...")
    conf_results = analyze_confidence_bands(df)
    print_table(conf_results, "League + Confidence Band Performance:")
    
    # Step 3: Calibration analysis
    print("\n[3/5] Analyzing calibration...")
    calib_results = analyze_calibration(df)
    print_table(calib_results, "Calibration (Expected vs Actual):")
    
    if len(calib_results) > 0:
        avg_error = calib_results['Error'].abs().mean()
        print(f"\n     Average Calibration Error: {avg_error:.1f}%")
        if avg_error < 5:
            print("     Status: GOOD - Model well-calibrated")
        elif avg_error < 10:
            print("     Status: ACCEPTABLE")
        else:
            print("     Status: NEEDS IMPROVEMENT")
    
    # Step 4: Loss concentration
    print("\n[4/5] Analyzing loss concentration...")
    loss_stats = analyze_loss_concentration(df)
    print(f"\n     Total Bets: {loss_stats.get('total_bets', 0)}")
    print(f"     Wins: {loss_stats.get('wins', 0)}")
    print(f"     Losses: {loss_stats.get('losses', 0)}")
    print(f"     Win Rate: {loss_stats.get('win_rate', 0):.1f}%")
    
    # Step 5: Optimal thresholds
    print("\n[5/5] Finding optimal thresholds...")
    optimal_results = find_optimal_thresholds(df)
    print_table(optimal_results, "Optimal Thresholds by League:")
    
    # Summary
    print("\n" + "="*70)
    print("  ANALYSIS COMPLETE")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()