from pqc_iot_sim.core.simulation import Simulation


def main():
    simulation = Simulation(config_path="configs/default.yaml")
    simulation.run()


if __name__ == "__main__":
    main()
