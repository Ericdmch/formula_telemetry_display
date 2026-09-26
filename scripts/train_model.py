import pandas as pd

from config import Config
from src.model import train_model


if __name__ == "__main__":
    config = Config()
    training = pd.read_csv(config.training_path)
    report = train_model(training, config.model_path)
    ordered_importance = sorted(
        report.feature_importances.items(), key=lambda item: item[1], reverse=True
    )
    text = (
        "Evaluation on held-out synthetic scenarios only. "
        "This is not real-world safety validation.\n\n"
        f"Confusion matrix (NORMAL, MODERATE_RISK, HIGH_RISK):\n"
        f"{report.confusion_matrix}\n\n"
        f"{report.classification_report}\n"
        "Feature importances (synthetic data; not causal):\n"
        + "\n".join(f"{name}: {value:.4f}" for name, value in ordered_importance)
        + "\n"
    )
    config.evaluation_path.write_text(text)
    print(f"Wrote model to {config.model_path}")
    print(text)
