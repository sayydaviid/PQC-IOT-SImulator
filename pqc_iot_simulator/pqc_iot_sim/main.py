"""Disponibiliza o ponto de entrada da linha de comando."""

from pathlib import Path
import json

from pqc_iot_simulator.pqc_iot_sim.core import Simulation


def main():
    """Executa o fluxo principal deste módulo."""
    config_path = Path(__file__).resolve().parent / "configs" / "default.yaml"
    simulation = Simulation(config_path=config_path)
    result = simulation.run()
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
