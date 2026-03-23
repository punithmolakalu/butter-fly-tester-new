class LIVProcess:
    def __init__(self, arroyo, gentec, recipe):
        """
        :param arroyo: Arroyo laser controller instance
        :param gentec: Gentec power meter instance
        :param recipe: Recipe object with min_current, max_current, current_step, etc.
        """
        self.arroyo = arroyo
        self.gentec = gentec
        self.recipe = recipe

    def run(self):
        min_current = self.recipe.min_current
        max_current = self.recipe.max_current
        current_step = self.recipe.current_step

        # Assign min/max current to Arroyo
        self.arroyo.set_max_current(max_current)  # Safety limit
        self.arroyo.set_current(min_current)      # Start at min current

        current = min_current
        power_readings = []
        voltage_readings = []

        while current <= max_current:
            self.arroyo.set_current(current)
            # Wait for current to settle if needed
            # time.sleep(self.recipe.settle_delay)

            # Take 10 power readings and average
            readings = [self.gentec.read_power() for _ in range(10)]
            avg_power = sum(readings) / len(readings)
            power_readings.append(avg_power)

            # Read voltage from Arroyo
            voltage = self.arroyo.read_voltage()
            voltage_readings.append(voltage)

            # Optionally: update live plot here

            current += current_step

        # Return results for further processing
        return {
            "currents": list(self._frange(min_current, max_current, current_step)),
            "powers": power_readings,
            "voltages": voltage_readings,
        }

    @staticmethod
    def _frange(start, stop, step):
        """Floating point range generator."""
        vals = []
        while start <= stop:
            vals.append(start)
            start += step
        return vals
