"""
Build Indian Loan Risk Model using the real Lending Club Loan Dataset.
Downloads from OpenML directly using scikit-learn.

This dataset (Lending-Club-Loan-Data) contains real borrower features:
fico, log.annual.inc, dti, revol.util, installment, days.with.cr.line, etc.
Target: not.fully.paid (1 = default, 0 = repaid)
"""
import os, sys, io
import numpy as np
import pandas as pd
import joblib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAVE_DIR = os.path.join(BASE_DIR, "ml_models", "saved")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)

FEATURES = [
    "credit_score", "annual_income", "employment_months",
    "existing_emi_amount", "loan_amount", "dti_ratio",
    "age", "credit_utilization", "existing_loans", "loan_type_idx"
]

def download_dataset():
    """Download the Lending Club Loan Dataset from OpenML."""
    from sklearn.datasets import fetch_openml
    print("[1/4] Downloading Lending Club dataset from OpenML (this may take a moment)...")
    
    # OpenML dataset: Lending-Club-Loan-Data (ID contains 9578 rows, 14 features)
    data = fetch_openml(name='Lending-Club-Loan-Data', version=1, as_frame=True, parser='auto')
    df = data.frame
    print(f"      Loaded {df.shape[0]} rows and {df.shape[1]} columns.")
    
    # Save the raw dataset for user inspection
    raw_path = os.path.join(DATA_DIR, "lending_club_raw.csv")
    df.to_csv(raw_path, index=False)
    print(f"      Raw dataset saved to: {raw_path}")
    return df

def map_raw_to_features(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Map the Lending Club fields into our expected schema:
    [credit_score, annual_income, employment_months, existing_emi_amount, 
     loan_amount, dti_ratio, age, credit_utilization, existing_loans, loan_type_idx]
    """
    print("[2/4] Mapping Lending Club data to our feature schema...")
    df = pd.DataFrame()
    
    # Drop rows with critical NaNs
    raw_df = raw_df.dropna(subset=['fico', 'log.annual.inc', 'dti', 'revol.util']).copy()

    # 1. Credit Score (FICO)
    df["credit_score"] = raw_df["fico"].astype(int)
    
    # 2. Annual Income (Stored as log.annual.inc, convert back to INR approx)
    # Lending club is USD, so we scale by roughly 80 to represent Indian context.
    usd_income = np.exp(raw_df["log.annual.inc"])
    df["annual_income"] = (usd_income * 80).astype(int)
    
    # 3. Existing EMI (Installment is monthly payment in USD)
    df["existing_emi_amount"] = (raw_df["installment"] * 80).astype(int)
    
    # 4. Loan Amount (Not explicit, but installment * 36 months is roughly loan + interest)
    # We estimate principal by multiplying installment * 30
    df["loan_amount"] = (raw_df["installment"] * 30 * 80).astype(int)
    
    # 5. DTI Ratio
    df["dti_ratio"] = raw_df["dti"].clip(0, 100)
    
    # 6. Credit Utilization (revol.util)
    df["credit_utilization"] = raw_df["revol.util"].clip(0, 100)
    
    # 7. Employment Months (Proxy: days.with.cr.line / 30)
    # The longer the credit line, usually the longer the employment history (cap at 20 yrs)
    months_cr = raw_df["days.with.cr.line"] / 30
    df["employment_months"] = np.clip(months_cr * 0.8, 6, 240).astype(int) 
    
    # 8. Age
    # Derived from credit line history (typically people start credit at 21)
    df["age"] = np.clip(21 + (raw_df["days.with.cr.line"] / 365), 21, 65).astype(int)
    
    # 9. Existing Loans / Inquiries (Proxy via inq.last.6mths + pub.rec)
    df["existing_loans"] = (raw_df["inq.last.6mths"] + raw_df["pub.rec"]).fillna(0).astype(int)
    
    # 10. Loan Type
    # purpose: 'debt_consolidation', 'credit_card', 'all_other', 'home_improvement', 'small_business', etc.
    # Map to index: 0=home, 1=personal/other, 2=business
    conditions = [
        raw_df['purpose'].str.contains('home', case=False, na=False),
        raw_df['purpose'].str.contains('business', case=False, na=False)
    ]
    choices = [0, 2] # 0 = home_loan, 2 = business_loan
    df["loan_type_idx"] = np.select(conditions, choices, default=1).astype(int) # default to personal
    
    # 11. Target (not.fully.paid) -> 1 = defaulted, 0 = repaid
    df["default"] = raw_df["not.fully.paid"].astype(int)
    
    # Ensure dataset is clean
    df = df.dropna()
    print(f"      Mapped {df.shape[0]} valid rows.")
    return df

def train_model(df: pd.DataFrame):
    from xgboost import XGBClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split, RandomizedSearchCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, roc_auc_score, f1_score
    from sklearn.ensemble import VotingClassifier
    from scipy.stats import uniform, randint
    
    print("[3/4] Hyperparameter tuning models on Lending Club dataset...")
    X = df[FEATURES].values
    y = df["default"].values
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42, stratify=y
    )
    
    pos_weight = (y == 0).sum() / max((y == 1).sum(), 1)
    class_weight_dict = {0: 1, 1: pos_weight}
    
    # 1. Tune XGBoost deeper
    print("  => Tuning XGBoost (Deep)...")
    xgb_param_dist = {
        'n_estimators': randint(200, 800),
        'max_depth': randint(2, 6),
        'learning_rate': uniform(0.005, 0.1),
        'subsample': uniform(0.5, 0.5),
        'colsample_bytree': uniform(0.5, 0.5),
        'gamma': uniform(0, 5)
    }
    xgb_base = XGBClassifier(scale_pos_weight=pos_weight, eval_metric="auc", random_state=42, verbosity=0)
    xgb_search = RandomizedSearchCV(xgb_base, param_distributions=xgb_param_dist, 
                                    n_iter=40, scoring='roc_auc', cv=5, random_state=42, n_jobs=-1)
    xgb_search.fit(X_train, y_train)
    best_xgb = xgb_search.best_estimator_
    
    # 2. Tune Random Forest deeper
    print("  => Tuning Random Forest (Deep)...")
    rf_param_dist = {
        'n_estimators': randint(200, 600),
        'max_depth': randint(4, 15),
        'min_samples_split': randint(2, 20),
        'min_samples_leaf': randint(1, 10)
    }
    rf_base = RandomForestClassifier(class_weight=class_weight_dict, random_state=42)
    rf_search = RandomizedSearchCV(rf_base, param_distributions=rf_param_dist, 
                                   n_iter=25, scoring='roc_auc', cv=5, random_state=42, n_jobs=-1)
    rf_search.fit(X_train, y_train)
    best_rf = rf_search.best_estimator_
    
    # 3. Tune HistGradientBoosting (scikit-learn's LightGBM implementation, very powerful)
    from sklearn.ensemble import HistGradientBoostingClassifier
    print("  => Tuning HistGradientBoosting (Deep)...")
    # Using sample weights in fit for imbalance
    sample_weights = np.where(y_train == 1, pos_weight, 1.0)
    hgb_param_dist = {
        'max_iter': randint(100, 500),
        'max_depth': randint(3, 10),
        'learning_rate': uniform(0.01, 0.15),
        'l2_regularization': uniform(0.0, 5.0)
    }
    hgb_base = HistGradientBoostingClassifier(random_state=42)
    hgb_search = RandomizedSearchCV(hgb_base, param_distributions=hgb_param_dist, 
                                   n_iter=30, scoring='roc_auc', cv=5, random_state=42, n_jobs=-1)
    # HistGradientBoosting supports sample_weight only via fit params, but RandomizedSearchCV handles fit_params poorly in some versions.
    # We will just rely on the deep tuning grid without class weights, or rely completely on XGB/Ensemble for class imbalance handling.
    hgb_search.fit(X_train, y_train)
    best_hgb = hgb_search.best_estimator_
    
    # 4. Tune Logistic Regression
    print("  => Tuning Logistic Regression (Deep)...")
    lr_param_dist = {
        'C': uniform(0.001, 20.0),
        'l1_ratio': uniform(0, 1),
        'solver': ['saga'],
        'penalty': ['elasticnet']
    }
    lr_base = LogisticRegression(class_weight=class_weight_dict, max_iter=3000, random_state=42)
    lr_search = RandomizedSearchCV(lr_base, param_distributions=lr_param_dist, 
                                   n_iter=20, scoring='roc_auc', cv=5, random_state=42, n_jobs=-1)
    lr_search.fit(X_train, y_train)
    best_lr = lr_search.best_estimator_
    
    # 5. Build Final Heavy Ensemble
    ensemble_model = VotingClassifier(
        estimators=[('xgb', best_xgb), ('rf', best_rf), ('hgb', best_hgb), ('lr', best_lr)],
        voting='soft'
    )

    
    models = {
        "XGBoost (Tuned)": best_xgb,
        "Random Forest (Tuned)": best_rf,
        "LogReg (Tuned)": best_lr,
        "Tuned Voting Ensemble": ensemble_model
    }
    
    best_model = None
    best_auc = -1
    best_name = ""
    
    print("\n  === Model Comparison ===")
    for name, model in models.items():
        if name == "Tuned Voting Ensemble":
            # Voting classifier must be fitted on training data as a whole
            model.fit(X_train, y_train)
            
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]
        
        auc = roc_auc_score(y_test, y_proba)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        
        print(f"  {name:25s} | AUC: {auc:.4f} | Acc: {acc:.4f} | F1: {f1:.4f}")
        
    print("\n  => Selecting Tuned Voting Ensemble as per instructions.")
    best_name = "Tuned Voting Ensemble"
    best_model = models[best_name]
    best_auc = roc_auc_score(y_test, best_model.predict_proba(X_test)[:, 1])
    
    return best_model, scaler, best_name

def save_model(model, scaler, best_name):
    model_path  = os.path.join(SAVE_DIR, "loan_risk_model.joblib")
    scaler_path = os.path.join(SAVE_DIR, "loan_risk_scaler.joblib")
    features_path = os.path.join(SAVE_DIR, "loan_risk_features.joblib")
    
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    joblib.dump(FEATURES, features_path)
    print(f"[4/4] Best Model ({best_name}) and scaler saved successfully to {SAVE_DIR}.")

if __name__ == "__main__":
    raw_df = download_dataset()
    mapped_df = map_raw_to_features(raw_df)
    best_model, scaler, best_name = train_model(mapped_df)
    save_model(best_model, scaler, best_name)
    print(f"\nTraining pipeline completed successfully using the REAL Lending Club Dataset! Best Model: {best_name}")
