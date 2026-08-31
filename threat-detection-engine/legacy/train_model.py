import xgboost as xgb
from sklearn.ensemble import IsolationForest, StackingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
import joblib

def build_refined_models(X, y, scale_weight):
    # Added L1 (alpha) and L2 (lambda) regularization to prevent overfitting
    xgb_base = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.01, 
        scale_pos_weight=scale_weight, reg_alpha=0.1, reg_lambda=1.0, random_state=42
    )
    
    stacking_clf = StackingClassifier(
        estimators=[('xgb', xgb_base), ('rf', RandomForestClassifier(max_depth=4))],
        final_estimator=LogisticRegression(), cv=5
    )
    stacking_clf.fit(X, y)
    joblib.dump(stacking_clf, 'models/stacking_escalation_engine.pkl')

    iso_forest = IsolationForest(n_estimators=200, contamination=0.03, random_state=42)
    iso_forest.fit(X)
    joblib.dump(iso_forest, 'models/isolation_forest_engine.pkl')