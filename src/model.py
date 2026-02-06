import math

import numpy as np

from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import fbeta_score
from sklearn.model_selection import train_test_split

class AkiModel:
    """
    AKI classifier using logistic regression with median imputation.

    Preprocessing:
    - replace ±inf with NaN
    - median-impute per feature column

    Prediction:
    - predict probabilities with logistic regression
    - apply a probability threshold to produce 0/1 predictions
    """

    def __init__(self, threshold=0.5, tune_threshold=False, tune_grid=None, random_state=0):
        self.random_state = random_state
        self.threshold = float(threshold)
        self.tune_threshold = bool(tune_threshold)
        
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError("threshold must be between 0 and 1.")
        
        self.tune_grid = (
            [float(t) for t in tune_grid]
            if tune_grid is not None
            else [t / 10 for t in range(1, 10)]  # 0.1 ... 0.9
        )

        self.imputer = SimpleImputer(strategy="median")
        self.clf = LogisticRegression(
            max_iter=1000,
            class_weight="balanced", # helps recall (important for F3)
            solver="lbfgs",
            random_state=random_state,
        )
        self.feature_columns = None

    
    def _validate_fit_inputs(self, X, y):
        if len(X) == 0:
            raise ValueError("Training feature matrix X is empty.")
        if len(X) != len(y):
            raise ValueError(f"X and y have different lengths: len(X)={len(X)} len(y)={len(y)}")


    def _align_and_clean(self, X, fit=False):
        """
        Align feature columns and replace ±inf with NaN.

        If fit=True, establish the feature column order from X (training data).
        """
        if fit:
            self.feature_columns = list(X.columns)
        elif self.feature_columns is None:
            raise RuntimeError("Model has not been fitted yet.")

        X_aligned = X.reindex(columns=self.feature_columns, fill_value=np.nan)
        return X_aligned.replace([math.inf, -math.inf], np.nan)
    

    def _fit_preprocess(self, X):
        X_clean = self._align_and_clean(X, fit=True)
        return self.imputer.fit_transform(X_clean)
    

    def _predict_preprocess(self, X):
        X_clean = self._align_and_clean(X, fit=False)
        return self.imputer.transform(X_clean)


    def _select_best_threshold(self, y_true, probabilities):
        """
        Select the decision threshold that maximizes the F3 score
        for the given true labels and predicted probabilities.
        """
        best_threshold = self.threshold
        best_f3 = -1.0

        for t in self.tune_grid:
            preds = (probabilities >= t).astype(int)
            f3 = fbeta_score(y_true, preds, beta=3, zero_division=0)
            if f3 > best_f3:
                best_f3 = f3
                best_threshold = float(t)

        return best_threshold


    def fit(self, X, y):
        self._validate_fit_inputs(X, y)

        if self.tune_threshold:
            # Validation split
            X_train, X_val, y_train, y_val = train_test_split(
                X,
                y,
                test_size=0.2,
                stratify=y,
                random_state=self.random_state,
            )

            # Fit on training split
            X_train_imp = self._fit_preprocess(X_train)
            self.clf.fit(X_train_imp, y_train)

            # Predict probabilities on validation split
            X_val_imp = self._predict_preprocess(X_val)
            probabilities = self.clf.predict_proba(X_val_imp)[:, 1]

            # Select threshold on validation data
            self.threshold = self._select_best_threshold(y_val, probabilities)

            # Refit on full dataset
            X_full_imp = self._fit_preprocess(X)
            self.clf.fit(X_full_imp, y)

        else:
            X_imp = self._fit_preprocess(X)
            self.clf.fit(X_imp, y)

        return self


    def predict(self, X):
        if len(X) == 0:
            return np.array([], dtype=int)

        X_imp = self._predict_preprocess(X)
        probs = self.clf.predict_proba(X_imp)[:, 1]
        return (probs >= self.threshold).astype(int)
