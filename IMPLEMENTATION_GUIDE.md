# Galvana Implementation Guide

## Project Structure

```
galvana/
├── apps/
│   └── web/                        # Next.js 14 App Router
│       ├── app/
│       │   ├── (auth)/            # Auth-protected routes
│       │   ├── api/               # API route handlers
│       │   └── runs/              # Run management UI
│       ├── components/
│       │   ├── ui/                # Radix UI + Tailwind
│       │   ├── charts/            # D3.js visualizations
│       │   └── simulation/        # Three.js 3D views
│       └── lib/
│           ├── api/               # API client
│           └── stores/            # Zustand stores
│
├── services/
│   ├── api/                       # FastAPI Gateway
│   │   ├── app/
│   │   │   ├── domain/           # Domain models
│   │   │   ├── api/              # Route handlers
│   │   │   ├── core/             # Core utilities
│   │   │   └── infrastructure/   # External integrations
│   │   └── tests/
│   │
│   ├── hal/                       # Hardware Abstraction Layer
│   │   ├── drivers/
│   │   │   ├── gamry.py
│   │   │   ├── biologic.py
│   │   │   └── mock.py
│   │   ├── protocols/
│   │   └── safety/
│   │
│   └── orchestrator/              # Job Orchestration
│       ├── scheduler/
│       ├── workers/
│       └── events/
│
├── workers/
│   ├── sim-fenicsx/              # FEniCSx Worker
│   │   ├── solvers/
│   │   ├── mesh/
│   │   └── physics/
│   │
│   └── sim-moose/                # MOOSE Worker
│       ├── kernels/
│       ├── materials/
│       └── executioners/
│
├── packages/
│   ├── sdk-py/                   # Python SDK
│   │   └── galvana/
│   │       ├── client.py
│   │       ├── models.py
│   │       └── streaming.py
│   │
│   └── sdk-js/                   # JavaScript SDK
│       └── src/
│           ├── client.ts
│           └── websocket.ts
│
├── infra/
│   ├── terraform/                # Infrastructure as Code
│   ├── helm/                     # Kubernetes Charts
│   └── compose/                  # Docker Compose
│
└── shared/
    ├── protos/                   # Protocol Buffers
    ├── schemas/                  # JSON/YAML Schemas
    └── types/                    # Shared TypeScript Types
```

## Core Implementation

### 1. Domain Layer (services/api/app/domain/)

```python
# domain/entities/run.py
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid

class RunStatus(Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"

@dataclass
class RunAggregate:
    """Aggregate root for simulation/experiment runs"""
    id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    type: str = "simulation"
    status: RunStatus = RunStatus.QUEUED
    scenario_id: Optional[str] = None
    engine: str = "auto"
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    events: List["DomainEvent"] = field(default_factory=list)
    
    def start(self) -> None:
        """Start the run with validation"""
        if self.status != RunStatus.QUEUED:
            raise InvalidStateTransition(f"Cannot start run in {self.status} state")
        
        self.status = RunStatus.STARTING
        self.started_at = datetime.utcnow()
        self._add_event(RunStartedEvent(self.id, self.started_at))
    
    def pause(self) -> None:
        """Pause a running simulation"""
        if self.status != RunStatus.RUNNING:
            raise InvalidStateTransition(f"Cannot pause run in {self.status} state")
        
        self.status = RunStatus.PAUSED
        self._add_event(RunPausedEvent(self.id))
    
    def complete(self, results: dict) -> None:
        """Mark run as completed with results"""
        if self.status not in [RunStatus.RUNNING, RunStatus.STARTING]:
            raise InvalidStateTransition(f"Cannot complete run in {self.status} state")
        
        self.status = RunStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self._add_event(RunCompletedEvent(self.id, results))
    
    def _add_event(self, event: "DomainEvent") -> None:
        """Add domain event to uncommitted events"""
        self.events.append(event)

# domain/value_objects/physics.py
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class PhysicsConfiguration:
    """Value object for physics configuration"""
    transport: str = "nernst_planck"
    electroneutral: bool = True
    potential_model: str = "poisson"
    heat_coupling: bool = False
    phase_field: bool = False
    
    def validate(self) -> None:
        """Validate physics configuration consistency"""
        if self.transport == "stefan_maxwell" and self.electroneutral:
            raise ValueError("Stefan-Maxwell requires non-electroneutral transport")
        
        if self.phase_field and not self.transport:
            raise ValueError("Phase field requires transport model")

# domain/services/simulation_engine.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
import asyncio

class SimulationEngine(ABC):
    """Domain service interface for simulation engines"""
    
    @abstractmethod
    async def solve(
        self,
        scenario: "Scenario",
        config: PhysicsConfiguration
    ) -> AsyncIterator["SolutionFrame"]:
        """Solve physics equations and stream results"""
        pass
    
    @abstractmethod
    async def validate_stability(self, solution: "Solution") -> "StabilityMetrics":
        """Check solution stability and convergence"""
        pass

class FEniCSxEngine(SimulationEngine):
    """FEniCSx simulation engine implementation"""
    
    async def solve(self, scenario, config):
        """Implement FEniCSx solver"""
        # Setup mesh
        mesh = self._create_mesh(scenario.geometry)
        
        # Define function spaces
        V = self._create_function_space(mesh, config)
        
        # Assemble weak form
        F = self._assemble_weak_form(V, scenario, config)
        
        # Time stepping
        t = 0.0
        dt = scenario.numerics.dt_initial
        
        while t < scenario.drive.t_end:
            # Solve nonlinear system
            solution = await self._solve_timestep(F, dt)
            
            # Check convergence
            if not self._check_convergence(solution):
                dt *= 0.5  # Adaptive time stepping
                continue
            
            # Yield frame
            yield SolutionFrame(
                time=t,
                solution=solution,
                dt=dt
            )
            
            t += dt
            dt = min(dt * 1.2, scenario.numerics.dt_max)
```

### 2. API Layer (services/api/app/api/)

```python
# api/routes/runs.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Optional, List
from sse_starlette.sse import EventSourceResponse
import asyncio

from ..domain.entities import RunAggregate
from ..domain.services import SimulationEngine
from ..infrastructure.repositories import RunRepository
from ..infrastructure.messaging import EventBus

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

@router.post("/", status_code=202)
async def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    repo: RunRepository = Depends(get_repository),
    event_bus: EventBus = Depends(get_event_bus),
    current_user: User = Depends(get_current_user)
) -> RunHandle:
    """Create and queue a new simulation or experiment run"""
    
    # Create aggregate
    run = RunAggregate(
        type=request.type,
        scenario_id=request.scenario_id,
        engine=request.engine or "auto"
    )
    
    # Validate permissions
    if not await authorize_action(current_user, "runs:create", run):
        raise HTTPException(403, "Insufficient permissions")
    
    # Persist run
    await repo.save(run)
    
    # Publish events
    for event in run.events:
        await event_bus.publish(event)
    
    # Queue for execution
    background_tasks.add_task(execute_run, run.id)
    
    return RunHandle(
        run_id=run.id,
        status=run.status,
        stream_url=f"/api/v1/runs/{run.id}/stream"
    )

@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str,
    channels: List[str] = Query(...),
    repo: RunRepository = Depends(get_repository),
    current_user: User = Depends(get_current_user)
) -> EventSourceResponse:
    """Stream real-time updates for a run"""
    
    # Get run
    run = await repo.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    
    # Authorize
    if not await authorize_action(current_user, "runs:read", run):
        raise HTTPException(403, "Insufficient permissions")
    
    async def event_generator():
        """Generate SSE events"""
        async with StreamSubscriber(run_id, channels) as subscriber:
            async for event in subscriber:
                yield {
                    "event": event.type,
                    "data": event.to_json(),
                    "id": event.id,
                    "retry": 1000
                }
    
    return EventSourceResponse(event_generator())

# api/routes/websocket.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json

class ConnectionManager:
    """WebSocket connection manager with rooms"""
    
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, room: str):
        """Accept connection and add to room"""
        await websocket.accept()
        if room not in self.connections:
            self.connections[room] = set()
        self.connections[room].add(websocket)
    
    def disconnect(self, websocket: WebSocket, room: str):
        """Remove connection from room"""
        self.connections[room].discard(websocket)
        if not self.connections[room]:
            del self.connections[room]
    
    async def broadcast(self, room: str, message: dict):
        """Broadcast message to all connections in room"""
        if room in self.connections:
            disconnected = set()
            for connection in self.connections[room]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.add(connection)
            
            # Clean up disconnected
            for conn in disconnected:
                self.disconnect(conn, room)

manager = ConnectionManager()

@router.websocket("/ws/runs/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for run streaming"""
    await manager.connect(websocket, run_id)
    
    try:
        # Subscribe to run events
        async with EventSubscriber(run_id) as subscriber:
            async for event in subscriber:
                await websocket.send_json({
                    "type": event.type,
                    "data": event.data,
                    "timestamp": event.timestamp.isoformat()
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket, run_id)
```

### 3. Infrastructure Layer (services/api/app/infrastructure/)

```python
# infrastructure/repositories/run_repository.py
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import json

from ...domain.entities import RunAggregate, RunStatus
from ..models import RunModel

class RunRepository:
    """Repository for Run aggregate persistence"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, run: RunAggregate) -> None:
        """Save or update run aggregate"""
        model = await self.session.get(RunModel, run.id)
        
        if not model:
            model = RunModel(
                id=run.id,
                type=run.type,
                status=run.status.value,
                scenario_id=run.scenario_id,
                engine=run.engine,
                created_at=run.created_at
            )
            self.session.add(model)
        else:
            model.status = run.status.value
            model.started_at = run.started_at
            model.completed_at = run.completed_at
        
        # Store events in outbox for reliable publishing
        for event in run.events:
            outbox_entry = EventOutboxModel(
                aggregate_id=run.id,
                event_type=event.__class__.__name__,
                event_data=json.dumps(event.to_dict()),
                created_at=event.occurred_at
            )
            self.session.add(outbox_entry)
        
        await self.session.commit()
    
    async def get(self, run_id: str) -> Optional[RunAggregate]:
        """Retrieve run by ID"""
        result = await self.session.execute(
            select(RunModel).where(RunModel.id == run_id)
        )
        model = result.scalar_one_or_none()
        
        if not model:
            return None
        
        return self._to_aggregate(model)
    
    def _to_aggregate(self, model: RunModel) -> RunAggregate:
        """Convert model to aggregate"""
        return RunAggregate(
            id=model.id,
            type=model.type,
            status=RunStatus(model.status),
            scenario_id=model.scenario_id,
            engine=model.engine,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at
        )

# infrastructure/messaging/event_bus.py
from typing import List, Optional
import asyncio
import json
from abc import ABC, abstractmethod

class EventBus(ABC):
    """Abstract event bus interface"""
    
    @abstractmethod
    async def publish(self, event: "DomainEvent") -> None:
        pass
    
    @abstractmethod
    async def subscribe(self, pattern: str) -> AsyncIterator["DomainEvent"]:
        pass

class KafkaEventBus(EventBus):
    """Kafka-based event bus implementation"""
    
    def __init__(self, bootstrap_servers: str):
        from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
        
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode()
        )
        self.consumer = AIOKafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode())
        )
    
    async def publish(self, event: DomainEvent) -> None:
        """Publish event to Kafka topic"""
        topic = f"galvana.{event.aggregate_type}.{event.event_type}"
        
        await self.producer.send(
            topic,
            value={
                "aggregate_id": event.aggregate_id,
                "event_type": event.event_type,
                "data": event.data,
                "occurred_at": event.occurred_at.isoformat(),
                "correlation_id": event.correlation_id
            }
        )
    
    async def subscribe(self, pattern: str) -> AsyncIterator[DomainEvent]:
        """Subscribe to events matching pattern"""
        self.consumer.subscribe(pattern=pattern)
        
        async for msg in self.consumer:
            yield DomainEvent.from_dict(msg.value)

# infrastructure/messaging/outbox_processor.py
import asyncio
from datetime import datetime, timedelta

class OutboxProcessor:
    """Process events from outbox table for reliable publishing"""
    
    def __init__(self, db_session, event_bus, batch_size=100):
        self.db_session = db_session
        self.event_bus = event_bus
        self.batch_size = batch_size
    
    async def run(self):
        """Main processing loop"""
        while True:
            try:
                await self.process_batch()
                await asyncio.sleep(1)  # Process every second
            except Exception as e:
                logger.error(f"Outbox processing error: {e}")
                await asyncio.sleep(5)
    
    async def process_batch(self):
        """Process a batch of outbox events"""
        # Get unpublished events
        events = await self.db_session.execute(
            select(EventOutboxModel)
            .where(EventOutboxModel.published_at.is_(None))
            .order_by(EventOutboxModel.created_at)
            .limit(self.batch_size)
        )
        
        for event_model in events:
            try:
                # Publish event
                event = DomainEvent.from_json(event_model.event_data)
                await self.event_bus.publish(event)
                
                # Mark as published
                event_model.published_at = datetime.utcnow()
                
            except Exception as e:
                event_model.retry_count += 1
                event_model.last_error = str(e)
        
        await self.db_session.commit()
```

### 4. Worker Implementation (workers/sim-fenicsx/)

```python
# workers/sim-fenicsx/solver.py
import dolfinx as dfx
from dolfinx import fem, mesh, plot
import numpy as np
from petsc4py import PETSc
import ufl

class ElectrochemistryFEMSolver:
    """FEniCSx-based electrochemistry solver"""
    
    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.mesh = None
        self.V = None  # Function space
        self.u = None  # Solution function
        
    def setup_mesh(self):
        """Create computational mesh"""
        geom = self.scenario["geometry"]
        
        if geom["type"] == "1D":
            self.mesh = mesh.create_interval(
                MPI.COMM_WORLD,
                nx=geom["mesh"]["elements"],
                points=[0.0, geom["length"]]
            )
        elif geom["type"] == "2D":
            self.mesh = mesh.create_rectangle(
                MPI.COMM_WORLD,
                points=[[0, 0], [geom["length"], geom["width"]]],
                n=[geom["mesh"]["nx"], geom["mesh"]["ny"]]
            )
    
    def setup_function_spaces(self):
        """Define function spaces for mixed formulation"""
        physics = self.scenario["physics"]
        
        # Concentration space (P2)
        P2 = ufl.FiniteElement("Lagrange", self.mesh.ufl_cell(), 2)
        
        # Potential space (P1)
        P1 = ufl.FiniteElement("Lagrange", self.mesh.ufl_cell(), 1)
        
        # Mixed element for coupled system
        if physics["potential_model"] == "poisson":
            element = ufl.MixedElement([P2, P1])
            self.V = fem.FunctionSpace(self.mesh, element)
        else:
            self.V = fem.FunctionSpace(self.mesh, P2)
        
        # Solution functions
        self.u = fem.Function(self.V)  # Current solution
        self.u_n = fem.Function(self.V)  # Previous timestep
    
    def assemble_system(self):
        """Assemble weak form for Nernst-Planck-Poisson"""
        # Test and trial functions
        if self.scenario["physics"]["potential_model"] == "poisson":
            c, phi = ufl.split(self.u)
            c_n, phi_n = ufl.split(self.u_n)
            v_c, v_phi = ufl.TestFunctions(self.V)
        else:
            c = self.u
            c_n = self.u_n
            v_c = ufl.TestFunction(self.V)
        
        # Parameters
        D = self.scenario["materials"]["electrolyte"]["species"][0]["D"]
        z = self.scenario["materials"]["electrolyte"]["species"][0]["z"]
        F = 96485.0  # Faraday constant
        R = 8.314    # Gas constant
        T = 298.0    # Temperature
        
        # Time discretization
        dt = self.dt
        theta = 0.5  # Crank-Nicolson
        
        # Nernst-Planck equation
        c_mid = theta * c + (1 - theta) * c_n
        
        # Flux
        if self.scenario["physics"]["potential_model"] == "poisson":
            grad_phi_mid = theta * ufl.grad(phi) + (1 - theta) * ufl.grad(phi_n)
            J = -D * (ufl.grad(c_mid) + z * F / (R * T) * c_mid * grad_phi_mid)
        else:
            J = -D * ufl.grad(c_mid)
        
        # Weak form for concentration
        F_c = ((c - c_n) / dt * v_c - ufl.inner(J, ufl.grad(v_c))) * ufl.dx
        
        # Add Butler-Volmer boundary condition
        if "left_electrode" in self.scenario["boundaries"]:
            j0 = self.scenario["kinetics"]["exchange_current_density"]
            alpha = self.scenario["kinetics"].get("alpha_a", 0.5)
            eta = phi - self.scenario["drive"]["waveform"]["V"]  # Overpotential
            
            # Butler-Volmer kinetics
            j_BV = j0 * (ufl.exp(alpha * F * eta / (R * T)) - 
                        ufl.exp(-(1 - alpha) * F * eta / (R * T)))
            
            F_c += j_BV * v_c * self.ds(1)  # Electrode boundary
        
        # Poisson equation for potential
        if self.scenario["physics"]["potential_model"] == "poisson":
            epsilon = 80.0  # Relative permittivity
            epsilon_0 = 8.854e-12  # Vacuum permittivity
            
            # Charge density
            rho = F * z * c_mid
            
            # Weak form for potential
            F_phi = (ufl.inner(ufl.grad(phi), ufl.grad(v_phi)) + 
                    rho / (epsilon * epsilon_0) * v_phi) * ufl.dx
            
            F = F_c + F_phi
        else:
            F = F_c
        
        return F
    
    async def solve_timestep(self):
        """Solve one timestep using Newton-Krylov"""
        F = self.assemble_system()
        
        # Create nonlinear problem
        problem = fem.petsc.NonlinearProblem(F, self.u)
        
        # Configure solver
        solver = dfx.nls.petsc.NewtonSolver(MPI.COMM_WORLD, problem)
        solver.convergence_criterion = "incremental"
        solver.rtol = 1e-8
        solver.max_it = 50
        
        # Krylov solver settings
        ksp = solver.krylov_solver
        ksp.setType("gmres")
        ksp.getPC().setType("ilu")
        
        # Solve
        n_iter, converged = solver.solve(self.u)
        
        if not converged:
            # Adaptive time stepping on failure
            self.dt *= 0.5
            return False
        
        # Update solution
        self.u_n.x.array[:] = self.u.x.array[:]
        
        return True
    
    async def run(self):
        """Main time-stepping loop"""
        self.setup_mesh()
        self.setup_function_spaces()
        
        t = 0.0
        self.dt = self.scenario["numerics"]["dt_initial"]
        t_end = self.scenario["drive"]["waveform"]["t_end"]
        
        while t < t_end:
            # Solve timestep
            success = await self.solve_timestep()
            
            if success:
                t += self.dt
                
                # Extract and yield solution
                yield self.extract_solution(t)
                
                # Adaptive time stepping
                self.dt = min(self.dt * 1.2, 
                            self.scenario["numerics"]["dt_max"])
    
    def extract_solution(self, time: float) -> dict:
        """Extract solution data for streaming"""
        # Get concentration and potential
        if self.scenario["physics"]["potential_model"] == "poisson":
            c, phi = self.u.split()
        else:
            c = self.u
            phi = None
        
        # Compute current density at electrode
        j = self.compute_current_density()
        
        return {
            "time": time,
            "current_density": j,
            "concentration": c.x.array.tolist(),
            "potential": phi.x.array.tolist() if phi else None,
            "mesh_coordinates": self.mesh.geometry.x.tolist()
        }
```

### 5. Frontend Implementation (apps/web/)

```typescript
// apps/web/app/runs/[id]/page.tsx
"use client";

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RunChart } from '@/components/charts/RunChart';
import { RunControls } from '@/components/simulation/RunControls';
import { useRunStore } from '@/lib/stores/run-store';
import { useWebSocket } from '@/lib/hooks/use-websocket';

export default function RunPage() {
  const params = useParams();
  const runId = params.id as string;
  const { run, frames, updateRun, addFrame } = useRunStore();
  
  // WebSocket connection for real-time updates
  const { sendMessage } = useWebSocket(`/ws/runs/${runId}`, {
    onMessage: (event) => {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'frame':
          addFrame(data.data);
          break;
        case 'status':
          updateRun({ status: data.data.status });
          break;
      }
    }
  });
  
  // Load run details
  useEffect(() => {
    fetch(`/api/v1/runs/${runId}`)
      .then(res => res.json())
      .then(data => updateRun(data));
  }, [runId]);
  
  const handlePause = () => {
    fetch(`/api/v1/runs/${runId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'pause' })
    });
  };
  
  const handleResume = () => {
    fetch(`/api/v1/runs/${runId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'resume' })
    });
  };
  
  if (!run) return <div>Loading...</div>;
  
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Run {runId}</h1>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status Card */}
        <Card>
          <CardHeader>
            <CardTitle>Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span>Status:</span>
                <span className="font-mono">{run.status}</span>
              </div>
              <div className="flex justify-between">
                <span>Progress:</span>
                <span>{run.progress?.percentage || 0}%</span>
              </div>
              <div className="flex justify-between">
                <span>Time:</span>
                <span>{run.progress?.current_time?.toFixed(2)}s</span>
              </div>
            </div>
          </CardContent>
        </Card>
        
        {/* Controls */}
        <Card>
          <CardHeader>
            <CardTitle>Controls</CardTitle>
          </CardHeader>
          <CardContent>
            <RunControls
              status={run.status}
              onPause={handlePause}
              onResume={handleResume}
              onAbort={() => {}}
            />
          </CardContent>
        </Card>
        
        {/* Metrics */}
        <Card>
          <CardHeader>
            <CardTitle>Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span>CPU:</span>
                <span>{run.metrics?.cpu_usage?.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span>Memory:</span>
                <span>{run.metrics?.memory_usage?.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span>Iterations:</span>
                <span>{run.metrics?.solver_iterations || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
      
      {/* Real-time Chart */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Current Density vs Time</CardTitle>
        </CardHeader>
        <CardContent className="h-96">
          <RunChart data={frames} />
        </CardContent>
      </Card>
    </div>
  );
}

// lib/stores/run-store.ts
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface RunState {
  run: Run | null;
  frames: Frame[];
  updateRun: (run: Partial<Run>) => void;
  addFrame: (frame: Frame) => void;
  clearFrames: () => void;
}

export const useRunStore = create<RunState>()(
  devtools(
    persist(
      (set) => ({
        run: null,
        frames: [],
        
        updateRun: (runUpdate) =>
          set((state) => ({
            run: state.run ? { ...state.run, ...runUpdate } : null
          })),
        
        addFrame: (frame) =>
          set((state) => ({
            frames: [...state.frames, frame].slice(-1000) // Keep last 1000
          })),
        
        clearFrames: () => set({ frames: [] })
      }),
      {
        name: 'run-storage',
        partialize: (state) => ({ run: state.run }) // Only persist run
      }
    )
  )
);

// components/charts/RunChart.tsx
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface RunChartProps {
  data: Frame[];
}

export function RunChart({ data }: RunChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  
  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;
    
    const svg = d3.select(svgRef.current);
    const margin = { top: 20, right: 30, bottom: 40, left: 50 };
    const width = svgRef.current.clientWidth - margin.left - margin.right;
    const height = svgRef.current.clientHeight - margin.top - margin.bottom;
    
    // Clear previous render
    svg.selectAll("*").remove();
    
    const g = svg.append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);
    
    // Scales
    const xScale = d3.scaleLinear()
      .domain(d3.extent(data, d => d.time) as [number, number])
      .range([0, width]);
    
    const yScale = d3.scaleLinear()
      .domain(d3.extent(data, d => d.current) as [number, number])
      .range([height, 0]);
    
    // Line generator
    const line = d3.line<Frame>()
      .x(d => xScale(d.time))
      .y(d => yScale(d.current))
      .curve(d3.curveMonotoneX);
    
    // Add axes
    g.append("g")
      .attr("transform", `translate(0,${height})`)
      .call(d3.axisBottom(xScale));
    
    g.append("g")
      .call(d3.axisLeft(yScale));
    
    // Add line
    g.append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", "steelblue")
      .attr("stroke-width", 2)
      .attr("d", line);
    
    // Add dots for last few points
    g.selectAll(".dot")
      .data(data.slice(-10))
      .enter().append("circle")
      .attr("class", "dot")
      .attr("cx", d => xScale(d.time))
      .attr("cy", d => yScale(d.current))
      .attr("r", 3)
      .attr("fill", "steelblue");
    
  }, [data]);
  
  return <svg ref={svgRef} className="w-full h-full" />;
}
```

## Deployment Configuration

### Docker Compose (infra/compose/production.yml)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: galvana
      POSTGRES_USER: galvana
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U galvana"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY}
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    volumes:
      - kafka_data:/var/lib/kafka/data

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - zookeeper_data:/var/lib/zookeeper/data

  api:
    build:
      context: ../../services/api
      dockerfile: Dockerfile
    depends_on:
      - postgres
      - redis
      - kafka
    environment:
      DATABASE_URL: postgresql://galvana:${DB_PASSWORD}@postgres:5432/galvana
      REDIS_URL: redis://redis:6379
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      S3_ENDPOINT: http://minio:9000
      S3_ACCESS_KEY: ${S3_ACCESS_KEY}
      S3_SECRET_KEY: ${S3_SECRET_KEY}
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  orchestrator:
    build:
      context: ../../services/orchestrator
      dockerfile: Dockerfile
    depends_on:
      - api
      - kafka
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      DATABASE_URL: postgresql://galvana:${DB_PASSWORD}@postgres:5432/galvana
    
  sim-fenicsx:
    build:
      context: ../../workers/sim-fenicsx
      dockerfile: Dockerfile
    depends_on:
      - orchestrator
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      S3_ENDPOINT: http://minio:9000
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '4'
          memory: 16G

  web:
    build:
      context: ../../apps/web
      dockerfile: Dockerfile
    environment:
      NEXT_PUBLIC_API_URL: http://api:8080
      NEXT_PUBLIC_WS_URL: ws://api:8080
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
  minio_data:
  kafka_data:
  zookeeper_data:
```

This implementation guide provides a solid foundation for building the Galvana platform with modern patterns and best practices. The architecture supports scaling, resilience, and maintainability while keeping the implementation pragmatic and achievable.