import sys
import time
import pandas as pd
import numpy as np
import re
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.utils.class_weight import compute_sample_weight
import warnings

warnings.filterwarnings('ignore')

def preprocess_data(df, is_train=True, encoder=None):

    # clean
    df_clean = df.copy()
    
    # change power, torque, car_age into num
    df_clean['power_bhp'] = df_clean['power'].str.extract(r'([\d\.]+)bhp').astype(float)
    df_clean['torque_nm'] = df_clean['torque'].str.extract(r'([\d\.]+)Nm').astype(float)
    
    def parse_age(age_str):
        if pd.isna(age_str): return 0
        years = re.search(r'(\d+)\s*years?', str(age_str))
        months = re.search(r'(\d+)\s*months?', str(age_str))
        y = int(years.group(1)) if years else 0
        m = int(months.group(1)) if months else 0
        return y * 12 + m
    df_clean['car_age_months'] = df_clean['car_age'].apply(parse_age)
    
    # clean features into feature count
    df_clean['feature_count'] = df_clean['features'].apply(lambda x: len(str(x).split(',')) if x != '[]' else 0)

    cols_to_drop = ['power', 'torque', 'car_age', 'features', 'vehicle_usage_type']
    
    # save policy_id for final output, drop it from features
    policy_ids = df_clean['policy_id'] if 'policy_id' in df_clean.columns else None
    if 'policy_id' in df_clean.columns:
        cols_to_drop.append('policy_id')
        
    df_clean = df_clean.drop(columns=cols_to_drop)
    
    # separate target variables
    y_reg = df_clean.pop('safety_rating') if is_train and 'safety_rating' in df_clean.columns else None
    y_clf = df_clean.pop('claim') if is_train and 'claim' in df_clean.columns else None
    
    cat_cols = df_clean.select_dtypes(include=['object', 'string', 'category']).columns.tolist()
    
    if is_train:
        encoder = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        df_clean[cat_cols] = encoder.fit_transform(df_clean[cat_cols])
    else:
        df_clean[cat_cols] = encoder.transform(df_clean[cat_cols])
        
    safe_cat_indices = []
    for col in cat_cols:
        if df_clean[col].nunique() <= 255:
            safe_cat_indices.append(df_clean.columns.get_loc(col))
            
    return df_clean, y_reg, y_clf, policy_ids, encoder, safe_cat_indices


def main():
    start_time = time.time()
    
    if len(sys.argv) != 3:
        print("Usage: python3 z5617485.py <train_file> <test_file>")
        sys.exit(1)
        
    train_path = sys.argv[1]
    test_path = sys.argv[2]
    
    try:
        train_df = pd.read_csv(train_path)
        test_df = pd.read_csv(test_path)
    except FileNotFoundError:
        print("Error: Could not find the specified dataset files.")
        sys.exit(1)
        
    X_train, y_train_reg, y_train_clf, _, encoder, cat_indices = preprocess_data(train_df, is_train=True)
    X_test, _, _, test_ids, _, _ = preprocess_data(test_df, is_train=False, encoder=encoder)
    
    
    # init models
    print("Training Regression Model (Safety Rating)...")
    reg_model = HistGradientBoostingRegressor(
        max_iter=300, 
        learning_rate=0.05, 
        max_depth=12, 
        categorical_features=cat_indices,
        random_state=42
    )
    reg_model.fit(X_train, y_train_reg)
    
    # pred
    test_safety_preds = reg_model.predict(X_test)
    
    # result
    reg_output = pd.DataFrame({'policy_id': test_ids, 'safety_rating': test_safety_preds})
    reg_output.to_csv('z5617485_regression.csv', index=False)
    print(" -> z5617485_regression.csv generated.")
    
    
    # classification model
    print("Training Classification Model (Claim)...")
    X_train_clf = X_train.copy()
    X_train_clf['safety_rating'] = y_train_reg
    
    X_test_clf = X_test.copy()
    X_test_clf['safety_rating'] = test_safety_preds
    
    # cal weight
    sample_weights = compute_sample_weight(class_weight='balanced', y=y_train_clf)
    
    clf_model = HistGradientBoostingClassifier(
        max_iter=400,
        learning_rate=0.05,
        max_depth=12,
        l2_regularization=0.5,
        categorical_features=cat_indices,
        random_state=42
    )
    clf_model.fit(X_train_clf, y_train_clf, sample_weight=sample_weights)
    
    clf_probs = clf_model.predict_proba(X_test_clf)[:, 1]
    test_claim_preds = (clf_probs >= 0.60).astype(int)
    
    # result
    clf_output = pd.DataFrame({'policy_id': test_ids, 'claim': test_claim_preds})
    clf_output.to_csv('z5617485_classification.csv', index=False)
    print(" -> z5617485_classification.csv generated.")
    
    elapsed_time = time.time() - start_time
    print(f"\\nAll tasks completed successfully in {elapsed_time:.2f} seconds!")

if __name__ == "__main__":
    main()