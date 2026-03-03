
class RiskMetrics:
    """Calculates and stores the industrial KPIs of a simulated strategy."""
    def __init__(self, capex_eur: float, cycle_life: int, capacity_mwh: float):
        self.capex_eur = capex_eur
        self.cycle_life = cycle_life
        self.capacity_mwh = capacity_mwh

        # Marginal LCOS
        self.marginal_lcos = capex_eur / (cycle_life * capacity_mwh * 2.0)

    def calculate_efc(self, total_throughput_mwh: float) -> float:
        """Equivalent Full Cycles"""
        return total_throughput_mwh / (self.capacity_mwh * 2.0)

    def calculate_rodc(self, net_pnl: float, efc: float) -> float:
        """
        Return on Degraded Capital.
        How many Euros of profit generated per Euro of battery life destroyed.
        """
        degradation_cost = efc * self.marginal_lcos * (self.capacity_mwh * 2.0)
        if degradation_cost == 0:
            return 0.0
        return net_pnl / degradation_cost

    def generate_report(self, gross_revenue: float, gross_cost: float, total_throughput_mwh: float) -> dict[str, float]:
        """Summarizes the run into KPIs."""
        gross_pnl = gross_revenue - gross_cost
        efc = self.calculate_efc(total_throughput_mwh)
        degradation_cost = efc * self.marginal_lcos * (self.capacity_mwh * 2.0)
        net_adjusted_pnl = gross_pnl - degradation_cost
        rodc = self.calculate_rodc(net_adjusted_pnl, efc)

        return {
            "Gross PnL (EUR)": round(gross_pnl, 2),
            "EFC (Cycles)": round(efc, 2),
            "LCOS Penalty (EUR)": round(degradation_cost, 2),
            "Net Adjusted PnL (EUR)": round(net_adjusted_pnl, 2),
            "RoDC (Ratio)": round(rodc, 3)
        }
