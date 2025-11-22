#!/usr/bin/env python3
"""
Simple 1D Nernst-Planck solver for MVP
Uses finite differences for easy setup without FEniCSx dependencies

SPRINT 2: Async generator with keyframe support for WebSocket streaming
"""

import asyncio
import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve
from typing import Dict, Any, Iterator, AsyncIterator
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleElectrochemistrySolver:
    """Simplified 1D electrochemistry solver for MVP"""
    
    def __init__(self, scenario: Dict[str, Any]):
        self.scenario = scenario
        
        # Extract parameters
        self.L = scenario["geometry"].get("length", 1e-3)  # m
        self.nx = scenario["geometry"].get("mesh", {}).get("elements", 100)
        self.dx = self.L / self.nx
        
        # Physics parameters
        physics = scenario.get("physics", {})
        self.transport = physics.get("transport", "nernst_planck")
        
        # Material properties
        materials = scenario.get("materials", {}).get("electrolyte", {})
        species = materials.get("species", [
            {"name": "Ni2+", "D": 6.7e-10, "z": 2, "c0": 1.0}  # mol/m³
        ])
        
        if species:
            self.D = species[0].get("D", 1e-9)  # Diffusivity m²/s
            self.z = species[0].get("z", 1)     # Charge
            self.c0 = species[0].get("c0", 1.0)  # Initial concentration mol/m³
        else:
            self.D = 1e-9
            self.z = 1
            self.c0 = 1.0
        
        # Kinetics
        kinetics = scenario.get("kinetics", {})
        self.j0 = kinetics.get("exchange_current_density", 1.0)  # A/m²
        self.alpha = kinetics.get("alpha_a", 0.5)
        
        # Drive conditions
        drive = scenario.get("drive", {})
        waveform = drive.get("waveform", {})
        self.V_applied = waveform.get("V", -0.8)  # V
        self.t_end = waveform.get("t_end", 120.0)  # s
        
        # Numerics
        numerics = scenario.get("numerics", {})
        self.dt = numerics.get("dt_initial", 1e-3)  # s
        self.save_interval = scenario.get("outputs", {}).get("cadence", 0.1)
        
        # Constants
        self.F = 96485.0  # Faraday constant C/mol
        self.R = 8.314    # Gas constant J/(mol·K)
        self.T = 298.0    # Temperature K
        
        # Initialize solution arrays
        self.x = np.linspace(0, self.L, self.nx + 1)
        self.c = np.ones(self.nx + 1) * self.c0
        self.phi = np.zeros(self.nx + 1)
        
    def solve(self) -> Iterator[Dict[str, Any]]:
        """
        Main time-stepping loop (synchronous)

        DEPRECATED: Use solve_async() for WebSocket streaming with backpressure
        """
        t = 0.0
        step = 0
        last_save = 0.0

        logger.info(f"Starting simulation: t_end={self.t_end}s, dt={self.dt}s")

        while t < self.t_end:
            # Update concentration
            self.update_concentration()

            # Update potential (simplified - linear distribution)
            self.update_potential()

            # Compute current density at electrode
            j = self.compute_current_density()

            # Save output at specified intervals
            if t - last_save >= self.save_interval:
                yield {
                    "time": t,
                    "timestep": step,
                    "current_density": float(j),
                    "concentration": self.c.tolist(),
                    "potential": self.phi.tolist(),
                    "x": self.x.tolist()
                }
                last_save = t

                if step % 100 == 0:
                    logger.info(f"t={t:.3f}s, j={j:.3e} A/m², c_surf={self.c[0]:.3e} mol/m³")

            t += self.dt
            step += 1

        # Final frame
        j = self.compute_current_density()
        yield {
            "time": t,
            "timestep": step,
            "current_density": float(j),
            "concentration": self.c.tolist(),
            "potential": self.phi.tolist(),
            "x": self.x.tolist()
        }

        logger.info(f"Simulation completed: {step} timesteps")

    async def solve_async(
        self,
        keyframe_interval: int = 10
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Async time-stepping loop with keyframe support for WebSocket streaming

        Args:
            keyframe_interval: Mark every Nth frame as keyframe (default: 10)

        Yields:
            Frame dictionaries with simulation data and keyframe flags

        Keyframe Strategy (Solarpunk Efficiency):
            - Every 10th frame is marked as keyframe (critical data)
            - Non-keyframes can be dropped by backpressure controller
            - Keyframes always preserve full state (concentration, potential)
            - Final frame is always a keyframe

        Example:
            solver = SimpleElectrochemistrySolver(scenario)
            async for frame in solver.solve_async():
                if frame["is_keyframe"]:
                    print(f"Keyframe at t={frame['time']}")
                await backpressure_controller.enqueue(frame, is_keyframe=frame["is_keyframe"])
        """
        t = 0.0
        step = 0
        save_step = 0  # Track which save step we're on
        last_save = 0.0

        logger.info(
            f"Starting async simulation: t_end={self.t_end}s, dt={self.dt}s, "
            f"keyframe_interval={keyframe_interval}"
        )

        while t < self.t_end:
            # Update concentration
            self.update_concentration()

            # Update potential (simplified - linear distribution)
            self.update_potential()

            # Compute current density at electrode
            j = self.compute_current_density()

            # Save output at specified intervals
            if t - last_save >= self.save_interval:
                # Determine if this is a keyframe (every 10th save by default)
                is_keyframe = (save_step % keyframe_interval == 0)

                frame = {
                    "type": "frame",
                    "time": t,
                    "timestep": step,
                    "save_step": save_step,
                    "is_keyframe": is_keyframe,
                    "data": {
                        "current_density": float(j),
                        "voltage": float(self.V_applied),
                        "concentration_surface": float(self.c[0]),
                        "concentration_bulk": float(self.c[-1]),
                    }
                }

                # Include full arrays only in keyframes (reduce bandwidth)
                if is_keyframe:
                    frame["data"]["concentration"] = self.c.tolist()
                    frame["data"]["potential"] = self.phi.tolist()
                    frame["data"]["x"] = self.x.tolist()

                yield frame

                last_save = t
                save_step += 1

                if step % 100 == 0:
                    logger.info(
                        f"t={t:.3f}s, j={j:.3e} A/m², c_surf={self.c[0]:.3e} mol/m³ "
                        f"[{'KEYFRAME' if is_keyframe else 'frame'}]"
                    )

            t += self.dt
            step += 1

            # Yield control to event loop (allow other tasks to run)
            await asyncio.sleep(0)

        # Final frame (always a keyframe)
        j = self.compute_current_density()
        final_frame = {
            "type": "frame",
            "time": t,
            "timestep": step,
            "save_step": save_step,
            "is_keyframe": True,  # Final frame is always critical
            "final": True,
            "data": {
                "current_density": float(j),
                "voltage": float(self.V_applied),
                "concentration_surface": float(self.c[0]),
                "concentration_bulk": float(self.c[-1]),
                "concentration": self.c.tolist(),
                "potential": self.phi.tolist(),
                "x": self.x.tolist()
            }
        }

        yield final_frame

        logger.info(
            f"Simulation completed: {step} timesteps, {save_step} frames saved, "
            f"{(save_step // keyframe_interval) + 1} keyframes"
        )
    
    def update_concentration(self):
        """Update concentration using implicit finite differences"""
        # Build tridiagonal matrix for diffusion
        r = self.D * self.dt / (self.dx ** 2)
        
        # Interior points: implicit diffusion
        main_diag = np.ones(self.nx + 1) * (1 + 2 * r)
        upper_diag = np.ones(self.nx) * (-r)
        lower_diag = np.ones(self.nx) * (-r)
        
        # Boundary conditions
        # Left (electrode): flux boundary condition
        main_diag[0] = 1 + r
        
        # Right (bulk): fixed concentration
        main_diag[-1] = 1
        upper_diag[-1] = 0
        lower_diag[-1] = 0
        
        # Assemble matrix
        A = diags([lower_diag, main_diag, upper_diag], 
                 offsets=[-1, 0, 1], 
                 shape=(self.nx + 1, self.nx + 1),
                 format='csr')
        
        # RHS
        b = self.c.copy()
        
        # Apply Butler-Volmer flux at electrode
        j = self.compute_current_density()
        flux = j / (self.z * self.F)  # mol/(m²·s)
        b[0] += r * flux * self.dx / self.D
        
        # Bulk boundary condition
        b[-1] = self.c0
        
        # Solve
        self.c = spsolve(A, b)
        
        # Ensure non-negative concentration
        self.c = np.maximum(self.c, 0.0)
    
    def update_potential(self):
        """Simple linear potential distribution"""
        # For MVP, assume linear drop from electrode to bulk
        self.phi = np.linspace(self.V_applied, 0, self.nx + 1)
    
    def compute_current_density(self) -> float:
        """Compute current density using Butler-Volmer kinetics"""
        # Surface concentration at electrode
        c_surf = self.c[0]
        
        # Overpotential
        eta = self.V_applied  # Simplified: vs reference
        
        # Butler-Volmer equation
        if c_surf > 0:
            j_forward = self.j0 * (c_surf / self.c0) * np.exp(
                self.alpha * self.z * self.F * eta / (self.R * self.T)
            )
            j_backward = self.j0 * np.exp(
                -(1 - self.alpha) * self.z * self.F * eta / (self.R * self.T)
            )
            j = j_forward - j_backward
        else:
            j = 0.0
        
        return j


def run_simulation(scenario_path: str = None, scenario_dict: Dict = None):
    """Run a simulation from scenario file or dict"""
    if scenario_path:
        with open(scenario_path, 'r') as f:
            if scenario_path.endswith('.yaml'):
                import yaml
                scenario = yaml.safe_load(f)
            else:
                scenario = json.load(f)
    elif scenario_dict:
        scenario = scenario_dict
    else:
        # Default scenario for testing
        scenario = {
            "name": "Simple 1D Electrodeposition",
            "geometry": {
                "type": "1D",
                "length": 1e-3,
                "mesh": {"elements": 100}
            },
            "physics": {
                "transport": "nernst_planck",
                "electroneutral": True
            },
            "materials": {
                "electrolyte": {
                    "species": [
                        {"name": "Ni2+", "D": 6.7e-10, "z": 2, "c0": 100.0}
                    ]
                }
            },
            "kinetics": {
                "model": "butler_volmer",
                "exchange_current_density": 2.0,
                "alpha_a": 0.5
            },
            "drive": {
                "mode": "potentiostatic",
                "waveform": {"type": "step", "V": -0.8, "t_end": 10.0}
            },
            "numerics": {
                "dt_initial": 1e-3
            },
            "outputs": {
                "save": ["current_density", "concentration", "potential"],
                "cadence": 0.1
            }
        }
    
    solver = SimpleElectrochemistrySolver(scenario)
    
    results = []
    for frame in solver.solve():
        results.append(frame)
        
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        results = run_simulation(scenario_path=sys.argv[1])
    else:
        results = run_simulation()
    
    # Save results
    with open("simulation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Simulation completed: {len(results)} frames saved")
    
    # Plot if matplotlib is available
    try:
        import matplotlib.pyplot as plt
        
        times = [r["time"] for r in results]
        currents = [r["current_density"] for r in results]
        
        plt.figure(figsize=(10, 6))
        plt.plot(times, currents, 'b-', linewidth=2)
        plt.xlabel("Time (s)")
        plt.ylabel("Current Density (A/m²)")
        plt.title("Electrodeposition Current vs Time")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig("current_vs_time.png")
        logger.info("Plot saved as current_vs_time.png")
    except ImportError:
        pass