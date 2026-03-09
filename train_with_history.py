"""
train_with_history.py
=====================
Train the FPL XGBoost model on all available historical seasons
(vaastav 2016-17 through 2023-24) plus the current processed data,
then evaluate on 2024-25 GW 34-38.

Run from repo root:
    python train_with_history.py
"""
import sys, os, warnings, json
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

# ── paths ──────────────────────────────────────────────────────────────────────
DATA_DIR     = 'data'
PROCESSED    = os.path.join(DATA_DIR, 'processed_fpl_data.csv')

# Seasons available in vaastav repo (2016-19 lack position/team in merged_gw)
HIST_SEASONS_FULL  = ['2020-21', '2021-22', '2022-23', '2023-24']   # position + team + xP
HIST_SEASONS_BASIC = ['2016-17', '2017-18', '2018-19', '2019-20']   # no position/team

# ── helpers ────────────────────────────────────────────────────────────────────

def load_season(season: str) -> pd.DataFrame | None:
    """Load a vaastav merged_gw.csv and standardise it."""
    path = os.path.join(DATA_DIR, season, 'gws', 'merged_gw.csv')
    if not os.path.exists(path):
        print(f'  [skip] {season}: file not found')
        return None
    try:
        df = pd.read_csv(path, encoding='latin-1')
    except Exception as e:
        print(f'  [skip] {season}: {e}')
        return None

    df['season'] = season

    # Normalise GW column (some files already have GW, some only 'round')
    if 'GW' not in df.columns and 'round' in df.columns:
        df['GW'] = df['round']

    # For basic-era seasons (no position/team), try to join from cleaned_players.csv
    if 'position' not in df.columns or 'team' not in df.columns:
        cp_path = os.path.join(DATA_DIR, season, 'cleaned_players.csv')
        if os.path.exists(cp_path):
            try:
                cp = pd.read_csv(cp_path, encoding='latin-1')
                # cleaned_players has 'element_type' (1=GK,2=DEF,3=MID,4=FWD) and 'team'
                pos_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
                if 'element_type' in cp.columns:
                    cp['position'] = cp['element_type'].map(pos_map)
                # Join on player id / element
                id_col = 'id' if 'id' in cp.columns else 'element'
                if id_col in cp.columns and 'element' in df.columns:
                    df = df.merge(
                        cp[[ id_col, 'position', 'team_code']].rename(
                            columns={id_col: 'element', 'team_code': 'team'}
                        ).drop_duplicates('element'),
                        on='element', how='left'
                    )
            except Exception:
                pass

    # Final guard: drop rows still missing position or team
    df = df.dropna(subset=['position', 'team'] if 'position' in df.columns and 'team' in df.columns else [])

    if df.empty or 'position' not in df.columns:
        print(f'  [skip] {season}: could not resolve position column')
        return None

    # Normalise position codes (old seasons used integers)
    pos_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD',
               '1': 'GK', '2': 'DEF', '3': 'MID', '4': 'FWD'}
    df['position'] = df['position'].replace(pos_map)

    # Keep only rows with valid FPL positions
    df = df[df['position'].isin(['GK', 'DEF', 'MID', 'FWD'])]

    # Ensure numeric types
    for col in ['total_points', 'minutes', 'goals_scored', 'assists',
                'clean_sheets', 'ict_index', 'creativity', 'threat',
                'influence', 'bps', 'bonus', 'value', 'transfers_in',
                'transfers_out', 'was_home']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # was_home: convert True/False or 1/0
    if 'was_home' in df.columns:
        df['was_home'] = df['was_home'].astype(float)

    has_xp = 'xP' in df.columns
    has_xg = 'expected_goals' in df.columns
    print(f'  Loaded {season}: {len(df):,} rows  (xP={has_xp}, xG={has_xg})')
    return df


def add_base_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add lag-safe rolling features used in the base FPLFeatureEngineer,
    grouped by name + season so seasons never bleed into each other.
    """
    df = df.sort_values(['name', 'season', 'GW']).reset_index(drop=True)
    grp = df.groupby(['name', 'season'])

    for col, windows in [
        ('total_points', [3, 5, 10]),
        ('minutes',      [3, 5]),
        ('ict_index',    [3, 5]),
        ('creativity',   [3, 5]),
        ('threat',       [3, 5]),
        ('influence',    [3, 5]),
        ('bps',          [3, 5]),
        ('bonus',        [3]),
        ('clean_sheets', [3, 5]),
        # goals_conceded intentionally omitted — let MasterFE compute it
        # for all rows so 2024-25 rows don't end up NaN after concat
    ]:
        if col not in df.columns:
            continue
        for w in windows:
            alias = f'{col}_last_{w}_avg'
            if alias not in df.columns:
                df[alias] = grp[col].transform(
                    lambda x: x.shift(1).rolling(w, min_periods=1).mean()
                )

    # season expanding mean (lag-safe)
    if 'total_points' in df.columns:
        df['season_avg_points'] = grp['total_points'].transform(
            lambda x: x.shift(1).expanding().mean()
        )

    # form vs season average (computed after alias map is applied in main())
    # NOTE: do NOT create alias columns here — they would exist in hist_fe but be
    # NaN for current (2024-25) rows after concat, blocking the alias map in main()

    # points std last 5
    df['points_std_last_5'] = grp['total_points'].transform(
        lambda x: x.shift(1).rolling(5, min_periods=1).std()
    ).fillna(0)

    # games played (cumcount, no shift needed — count of previous games)
    df['games_played'] = grp.cumcount()

    return df


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    np.random.seed(42)

    # ── 1. Load historical seasons ────────────────────────────────────────────
    print('=' * 60)
    print('LOADING HISTORICAL SEASONS')
    print('=' * 60)

    hist_frames = []
    for s in HIST_SEASONS_FULL + HIST_SEASONS_BASIC:
        df_s = load_season(s)
        if df_s is not None:
            hist_frames.append(df_s)

    if not hist_frames:
        print('No historical data found.')
        return

    hist_raw = pd.concat(hist_frames, ignore_index=True)
    print(f'\nTotal historical rows loaded: {len(hist_raw):,}')
    print(f'Seasons: {sorted(hist_raw["season"].unique())}')

    # ── 2. Apply base rolling features to historical data ────────────────────
    print('\nApplying base rolling features to historical data...')
    hist_fe = add_base_rolling_features(hist_raw)

    # ── 3. Load current processed data (2024-25 and 2025-26) ─────────────────
    print('\nLoading current processed data...')
    current = pd.read_csv(PROCESSED)
    print(f'Current data rows: {len(current):,}')

    # ── 4. Combine ────────────────────────────────────────────────────────────
    combined = pd.concat([hist_fe, current], ignore_index=True)
    combined = combined.sort_values(['name', 'season', 'GW']).reset_index(drop=True)
    n_seasons = combined['season'].nunique()
    print(f'\nCombined dataset: {len(combined):,} rows across {n_seasons} seasons')

    # ── 5. Run MasterFPLFeatureEngineer ───────────────────────────────────────
    # NOTE: bootstrap set-piece features (is_pen_taker etc.) tested but gave zero
    # improvement — historical rows filled with 0 created misleading noise for the
    # model. These features are valuable for live single-GW predictions only.
    print()
    from analysis.master_feature_engineering import MasterFPLFeatureEngineer
    me = MasterFPLFeatureEngineer(combined)
    combined = me.create_all_master_features()

    # Aliases and interaction terms
    for pos in ['GK', 'DEF', 'MID', 'FWD']:
        combined[f'position_{pos}'] = (combined['position'] == pos).astype(int)

    alias_map = {
        'total_points_last_3_avg':      'last_3_avg_points',
        'total_points_last_5_avg':      'last_5_avg_points',
        'total_points_last_10_avg':     'last_10_avg_points',
        'minutes_last_3_avg':           'last_3_avg_minutes',
        'ict_index_last_3_avg':         'ict_index_last_3',
        'ict_index_last_5_avg':         'ict_index_last_5',
        'creativity_last_3_avg':        'creativity_last_3',
        'threat_last_3_avg':            'threat_last_3',
        'clean_sheets_last_3_avg':      'cs_rate_last_3',
        'goals_conceded_last_3_avg':    'goals_conceded_last_3',
    }
    for src, dst in alias_map.items():
        if src in combined.columns:
            combined[dst] = combined[src]   # always overwrite — fixes NaN for 2024-25 rows
    if 'clean_sheets_last_3_avg' in combined.columns:
        combined['cs_per_game'] = combined['clean_sheets_last_3_avg']

    # form vs season average (now that last_5_avg_points and season_avg_points exist)
    if 'last_5_avg_points' in combined.columns and 'season_avg_points' in combined.columns:
        combined['form_vs_average'] = combined['last_5_avg_points'] - combined['season_avg_points']

    _enc = {'GK': 0, 'DEF': 1, 'MID': 2, 'FWD': 3, 'AM': 2}
    if 'opponent_strength' in combined.columns:
        combined['pos_x_opp_strength'] = (
            combined['position'].map(_enc) * combined['opponent_strength'].fillna(0)
        )
    combined['is_attacker'] = combined['position'].isin(['MID', 'FWD', 'AM']).astype(int)
    if 'xP_last_3' in combined.columns:
        combined['attacker_x_xP'] = combined['is_attacker'] * combined['xP_last_3'].fillna(0)
        combined['home_x_xP']     = combined['was_home'].astype(float) * combined['xP_last_3'].fillna(0)

    # ── 6. Define features ────────────────────────────────────────────────────
    CANDIDATE_FEATURES = [
        # Core form
        'last_3_avg_points', 'last_5_avg_points', 'last_10_avg_points',
        'last_3_avg_minutes', 'ewm_points',
        'season_avg_points', 'form_vs_average', 'points_std_last_5',
        # Minutes / rotation
        'avg_minutes_last_3', 'avg_minutes_last_5', 'minutes_trend',
        'blank_gw_last', 'blank_rate_last_5',
        'starts_per_90',                         # season-level rotation signal
        # xP / xG
        'xP_last_3', 'xP_last_5', 'xP_ewm',
        'expected_goals_last_3', 'expected_assists_last_3',
        'expected_goals_last_5', 'expected_assists_last_5',
        'expected_goal_involvements_last_3', 'xGI_last_3',
        # Per-90 rates (lagged)
        'goals_per_90_last_3', 'goals_per_90_last_5',
        'assists_per_90_last_3', 'bonus_per_90_last_3',
        # ICT
        'ict_index_last_3', 'ict_index_last_5',
        'creativity_last_3', 'threat_last_3', 'bps_last_3',
        # Team / defensive
        'team_goals_last_3',
        'cs_rate_last_3', 'goals_conceded_last_3', 'team_cs_rate_last_3',
        # opponent_clean_sheet_rate excluded — NaN for all historical seasons
        # Position
        'position_GK', 'position_DEF', 'position_MID', 'position_FWD',
        'is_attacker',
        # Fixture / home
        'was_home', 'value', 'games_played',
        'opponent_strength', 'pos_x_opp_strength',
        # Transfers / momentum
        'transfer_momentum', 'attacker_x_xP', 'home_x_xP',
        'team_total_points_last_gw', 'cs_per_game', 'availability_weight',
    ]
    FEATURES = [f for f in CANDIDATE_FEATURES if f in combined.columns]
    print(f'\nFeatures available: {len(FEATURES)} / {len(CANDIDATE_FEATURES)}')
    missing = set(CANDIDATE_FEATURES) - set(FEATURES)
    if missing:
        print(f'Missing: {sorted(missing)}')

    # ── 7. Walk-forward CV on 2024-25 GW 34-38 ───────────────────────────────
    print('\n' + '=' * 60)
    print('WALK-FORWARD CV  (trained on ALL history + 2024-25 GW1-N)')
    print('=' * 60)

    XGB_PARAMS = dict(
        n_estimators=500, learning_rate=0.02, max_depth=4,
        subsample=0.7, colsample_bytree=0.7, min_child_weight=5,
        reg_alpha=0.5, reg_lambda=2.0, gamma=0.1,
        random_state=42, verbosity=0,
        early_stopping_rounds=30, eval_metric='mae',
    )

    test_season  = '2024-25'
    hist_seasons = [s for s in combined['season'].unique() if s != test_season]

    # Historical rows (full seasons) used as permanent training base
    hist_base = combined[combined['season'].isin(hist_seasons)].dropna(
        subset=FEATURES + ['total_points']
    )

    results = []
    topk_rows = []

    # GW10-38: enough prior 2024-25 context for rolling features, full season coverage
    test_gws = list(range(10, 39))
    print(f'Testing GW {test_gws[0]}-{test_gws[-1]}  ({len(test_gws)} folds)')

    for test_gw in test_gws:
        cur_train = combined[
            (combined['season'] == test_season) & (combined['GW'] < test_gw)
        ].dropna(subset=FEATURES + ['total_points'])

        test_df = combined[
            (combined['season'] == test_season) & (combined['GW'] == test_gw)
        ].dropna(subset=FEATURES + ['total_points']).copy()

        if test_df.empty:
            continue

        train_df = pd.concat([hist_base, cur_train], ignore_index=True)

        split = int(len(train_df) * 0.9)
        X_tr, y_tr = train_df[FEATURES].iloc[:split], train_df['total_points'].iloc[:split]
        X_val, y_val = train_df[FEATURES].iloc[split:], train_df['total_points'].iloc[split:]

        mdl = XGBRegressor(**XGB_PARAMS)
        mdl.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        preds = mdl.predict(test_df[FEATURES])
        test_df['pred'] = preds

        mae  = mean_absolute_error(test_df['total_points'], preds)
        rmse = np.sqrt(mean_squared_error(test_df['total_points'], preds))
        r2   = r2_score(test_df['total_points'], preds)
        sp   = spearmanr(test_df['total_points'], preds).statistic

        topk = {}
        for k in [5, 10, 15, 20, 30]:
            top_pred   = set(test_df.nlargest(k, 'pred').index)
            top_actual = set(test_df.nlargest(k, 'total_points').index)
            topk[k]    = len(top_pred & top_actual) / k
        topk_rows.append(topk)

        print(f'  GW{test_gw:<3} train={len(train_df):,}  test={len(test_df):>4} '
              f' MAE={mae:.3f}  R²={r2:.3f}  Sp={sp:.3f} '
              f' T10={topk[10]:.0%}  T30={topk[30]:.0%}')

        results.append({'gw': test_gw, 'mae': mae, 'rmse': rmse, 'r2': r2, 'spearman': sp,
                        **{f'top{k}': topk[k] for k in [5,10,15,20,30]}})

    # ── 8. Summary ────────────────────────────────────────────────────────────
    print('\n' + '=' * 60)
    print(f'SUMMARY — GW10-38  ({len(results)} folds)')
    print('=' * 60)
    for metric in ['mae', 'rmse', 'r2', 'spearman']:
        vals = [r[metric] for r in results]
        print(f'  {metric.upper():<12}: {np.mean(vals):.3f} ± {np.std(vals):.3f}')

    # Phase breakdown: early (10-19), mid (20-29), late (30-38)
    phases = [('Early  GW10-19', range(10,20)), ('Mid    GW20-29', range(20,30)), ('Late   GW30-38', range(30,39))]
    print()
    print('  Phase breakdown:')
    for label, gw_range in phases:
        sub = [r for r in results if r['gw'] in gw_range]
        if not sub: continue
        m = np.mean([r['mae'] for r in sub])
        s = np.mean([r['spearman'] for r in sub])
        t10 = np.mean([r['top10'] for r in sub])
        t30 = np.mean([r['top30'] for r in sub])
        print(f'    {label}:  MAE={m:.3f}  Sp={s:.3f}  Top10={t10:.0%}  Top30={t30:.0%}')

    print()
    means = {k: np.mean([t[k] for t in topk_rows]) for k in [5,10,15,20,30]}
    print(f'  Top-K (mean across all GWs):')
    print(f'    Top5={means[5]:.0%}  Top10={means[10]:.0%}  Top15={means[15]:.0%}  '
          f'Top20={means[20]:.0%}  Top30={means[30]:.0%}')

    print()
    print('Prev benchmark (GW34-38 only, clean):')
    print('  MAE=0.996  R²=0.353  Spearman=0.721')
    print('  Top10=10%  Top30=36%')

    # ── 9. Final model — train on ALL available data and save ─────────────────
    print('\n' + '=' * 60)
    print('TRAINING FINAL MODEL ON ALL DATA')
    print('=' * 60)

    all_data = combined.dropna(subset=FEATURES + ['total_points'])
    X_all = all_data[FEATURES]
    y_all = all_data['total_points']

    # 90/10 internal split for early stopping only
    split = int(len(all_data) * 0.9)
    X_tr, y_tr = X_all.iloc[:split], y_all.iloc[:split]
    X_val, y_val = X_all.iloc[split:], y_all.iloc[split:]

    final_model = XGBRegressor(**XGB_PARAMS)
    final_model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    print(f'  Trained on {len(all_data):,} rows  '
          f'(best iteration: {final_model.best_iteration})')

    # Save model artifacts
    import json as _json, pickle, datetime
    os.makedirs('models', exist_ok=True)

    model_path_pkl  = os.path.join('models', 'xgb_history_v2.pkl')
    model_path_json = os.path.join('models', 'xgb_history_v2.json')
    meta_path       = os.path.join('models', 'xgb_history_v2_metadata.json')

    with open(model_path_pkl, 'wb') as f:
        pickle.dump(final_model, f)
    final_model.save_model(model_path_json)

    avg_mae  = np.mean([r['mae'] for r in results])
    avg_sp   = np.mean([r['spearman'] for r in results])
    avg_r2   = np.mean([r['r2'] for r in results])
    avg_t10  = np.mean([r['top10'] for r in results])
    avg_t30  = np.mean([r['top30'] for r in results])

    metadata = {
        'model': {
            'name': 'xgb_history_v2',
            'version': '2.0',
            'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'XGBRegressor',
            'description': (
                'XGBoost FPL points predictor trained on 4 historical seasons '
                '(2020-24) plus 2024-25. Walk-forward CV validated on GW10-38.'
            ),
        },
        'training': {
            'seasons': ['2020-21', '2021-22', '2022-23', '2023-24', '2024-25'],
            'total_rows': int(len(all_data)),
            'features': FEATURES,
            'n_features': len(FEATURES),
            'target': 'total_points',
            'params': XGB_PARAMS,
        },
        'cv_performance': {
            'method': 'walk-forward CV, GW10-38 of 2024-25',
            'n_folds': len(results),
            'mae_mean': round(avg_mae, 4),
            'r2_mean': round(avg_r2, 4),
            'spearman_mean': round(avg_sp, 4),
            'top10_precision_mean': round(avg_t10, 4),
            'top30_precision_mean': round(avg_t30, 4),
        },
        'usage': {
            'load': "import pickle; model = pickle.load(open('models/xgb_history_v2.pkl','rb'))",
            'predict': 'model.predict(feature_df[FEATURES])',
            'features': 'See training.features list above',
            'preprocessing': 'Apply MasterFPLFeatureEngineer.create_all_master_features()',
        },
    }

    with open(meta_path, 'w') as f:
        _json.dump(metadata, f, indent=2)

    print(f'\n  Saved:')
    print(f'    {model_path_pkl}')
    print(f'    {model_path_json}')
    print(f'    {meta_path}')
    print(f'\n  CV summary baked into metadata:')
    print(f'    MAE={avg_mae:.3f}  R²={avg_r2:.3f}  '
          f'Spearman={avg_sp:.3f}  Top10={avg_t10:.0%}  Top30={avg_t30:.0%}')


if __name__ == '__main__':
    main()
