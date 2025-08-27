#!/usr/bin/env python3
"""
Demo script to test the MVP implementation
"""

import sys
import os
import json
import time
import asyncio
import httpx
import yaml
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the solver directly
from workers.sim_fenicsx.simple_solver import SimpleElectrochemistrySolver

API_URL = "http://localhost:8080"


async def create_scenario(client: httpx.AsyncClient, scenario_path: str) -> str:
    """Create a scenario via API"""
    with open(scenario_path, 'r') as f:
        scenario = yaml.safe_load(f)
    
    response = await client.post(f"{API_URL}/api/v1/scenarios", json=scenario)
    response.raise_for_status()
    
    result = response.json()
    print(f"Created scenario: {result['id']}")
    return result['id']


async def create_run(client: httpx.AsyncClient, scenario_id: str) -> str:
    """Create a simulation run via API"""
    response = await client.post(
        f"{API_URL}/api/v1/runs",
        json={
            "type": "simulation",
            "scenario_id": scenario_id,
            "engine": "fenicsx",
            "tags": ["demo", "mvp"]
        }
    )
    response.raise_for_status()
    
    result = response.json()
    print(f"Created run: {result['run_id']}")
    return result['run_id']


async def monitor_run(client: httpx.AsyncClient, run_id: str):
    """Monitor run progress"""
    while True:
        response = await client.get(f"{API_URL}/api/v1/runs/{run_id}")
        response.raise_for_status()
        
        run = response.json()
        status = run['status']
        progress = run.get('progress', {})
        
        print(f"Run {run_id}: {status}", end="")
        if progress:
            print(f" - {progress.get('percentage', 0)}%", end="")
        print()
        
        if status in ['completed', 'failed', 'aborted']:
            break
        
        await asyncio.sleep(2)
    
    return run


def run_local_simulation(scenario_path: str):
    """Run simulation locally for testing"""
    print("\n=== Running Local Simulation ===")
    
    with open(scenario_path, 'r') as f:
        scenario = yaml.safe_load(f)
    
    solver = SimpleElectrochemistrySolver(scenario)
    
    results = []
    start_time = time.time()
    
    for i, frame in enumerate(solver.solve()):
        results.append(frame)
        
        if i % 10 == 0:
            print(f"  t={frame['time']:.2f}s, j={frame['current_density']:.3e} A/m²")
    
    elapsed = time.time() - start_time
    print(f"\nSimulation completed in {elapsed:.2f}s")
    print(f"Generated {len(results)} frames")
    
    # Save results
    output_path = "demo_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {output_path}")
    
    # Create a simple plot if matplotlib is available
    try:
        import matplotlib.pyplot as plt
        
        times = [r['time'] for r in results]
        currents = [r['current_density'] for r in results]
        
        plt.figure(figsize=(10, 6))
        plt.plot(times, currents, 'b-', linewidth=2)
        plt.xlabel('Time (s)')
        plt.ylabel('Current Density (A/m²)')
        plt.title('Nickel Plating Current vs Time')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        plot_path = "demo_plot.png"
        plt.savefig(plot_path)
        print(f"Plot saved to {plot_path}")
        
    except ImportError:
        print("matplotlib not available - skipping plot")
    
    return results


async def test_api():
    """Test the API endpoints"""
    print("\n=== Testing API Endpoints ===")
    
    async with httpx.AsyncClient() as client:
        # Health check
        response = await client.get(f"{API_URL}/health")
        if response.status_code == 200:
            print("✓ API is healthy")
        else:
            print("✗ API health check failed")
            return
        
        # Create scenario
        scenario_path = "examples/scenarios/ni_plating_mvp.yaml"
        scenario_id = await create_scenario(client, scenario_path)
        
        # Create run
        run_id = await create_run(client, scenario_id)
        
        # Monitor progress
        final_status = await monitor_run(client, run_id)
        
        if final_status['status'] == 'completed':
            print("✓ Run completed successfully")
        else:
            print(f"✗ Run ended with status: {final_status['status']}")
        
        # List runs
        response = await client.get(f"{API_URL}/api/v1/runs")
        runs = response.json()
        print(f"\nTotal runs: {len(runs)}")


def main():
    """Main demo function"""
    print("=" * 50)
    print("Galvana MVP Demo")
    print("=" * 50)
    
    scenario_path = "examples/scenarios/ni_plating_mvp.yaml"
    
    # Check if scenario file exists
    if not Path(scenario_path).exists():
        print(f"Error: Scenario file not found: {scenario_path}")
        return
    
    # Run local simulation
    results = run_local_simulation(scenario_path)
    
    # Test API if available
    try:
        response = httpx.get(f"{API_URL}/health", timeout=2.0)
        if response.status_code == 200:
            print("\nAPI is running - testing endpoints...")
            asyncio.run(test_api())
        else:
            print("\nAPI returned non-200 status")
    except (httpx.ConnectError, httpx.TimeoutException):
        print("\nAPI not available - run 'make api' to start it")
    
    print("\n" + "=" * 50)
    print("Demo completed!")
    print("\nNext steps:")
    print("1. Run 'make up' to start infrastructure")
    print("2. Run 'make api' to start the API server")
    print("3. Run 'make web' to start the web interface")
    print("4. Open http://localhost:3000 in your browser")
    print("=" * 50)


if __name__ == "__main__":
    main()