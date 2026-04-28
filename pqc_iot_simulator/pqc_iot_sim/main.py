from pathlib import Path

from pqc_iot_simulator.pqc_iot_sim.core import Simulation


def main():
    config_path = Path(__file__).resolve().parent / "configs" / "default.yaml"
    simulation = Simulation(config_path=config_path)
    simulation.run()


if __name__ == "__main__":
    main()
