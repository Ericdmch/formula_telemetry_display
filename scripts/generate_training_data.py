from config import Config
from src.model import generate_training_data


if __name__ == "__main__":
    config = Config()
    table = generate_training_data(seed=42, per_class=1200)
    config.training_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(config.training_path, index=False)
    print(f"Wrote {len(table)} synthetic rows to {config.training_path}")
