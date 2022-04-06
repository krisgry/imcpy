"""
Illustrates how to run an actor which responds to console input (e.g. over ssh).
"""


import logging
import sys
from typing import Tuple
import asyncio

import imcpy
from imcpy.actors.dynamic import DynamicActor
from imcpy.decorators import Subscribe, RunOnce

logger = logging.getLogger('examples.KeyboardActor')


class KeyboardActor(DynamicActor):
    def __init__(self, target_name):
        """
        Initialize the actor
        :param target_name: The name of the target system
        """
        super().__init__()
        self.target_name = target_name
        self.estate = None

        # This list contains the target systems to maintain communications with
        self.heartbeat.append(target_name)

    def from_target(self, msg):
        try:
            node = self.resolve_node_id(msg)
            return node.name == self.target_name
        except KeyError:
            return False

    @Subscribe(imcpy.EstimatedState)
    def recv_estate(self, msg: imcpy.EstimatedState):
        if self.from_target(msg):
            if self.estate is None:
                logger.info('Target connected')
            self.estate = msg

    def on_console(self, line):
        if line == 'exit':
            # Exit actor (terminate)
            logger.info('Stopping...')
            self.stop()
        elif line == 'stop':
            # Stop vehicle
            try:
                logger.info('Aborting...')
                abort = imcpy.Abort()
                self.send(self.target_name, abort)
            except KeyError:
                logger.error('Failed to send abort')
        elif line == 'start':
            # Send vehicle 100 meters north of its current position
            if self.estate is None:
                logger.info('Vehicle not connected')
            else:
                logger.info('Starting...')
                # Compute vehicle lat/lon
                lat, lon, hae = imcpy.coordinates.toWGS84(self.estate)

                # Define maneuver
                man = imcpy.Goto()
                man.z = 0.0
                man.z_units = imcpy.ZUnits.DEPTH
                man.lat, man.lon = imcpy.coordinates.WGS84.displace(lat, lon, n=100.0, e=0.0)
                man.speed = 1.2
                man.speed_units = imcpy.SpeedUnits.METERS_PS

                # Add to PlanManeuver message
                pman = imcpy.PlanManeuver()
                pman.data = man
                pman.maneuver_id = 'TestManeuver'

                # Add to PlanSpecification
                spec = imcpy.PlanSpecification()
                spec.plan_id = 'TestPlan'
                spec.maneuvers.append(pman)
                spec.start_man_id = 'TestManeuver'
                spec.description = 'A test plan sent from imcpy'

                # Start plan
                pc = imcpy.PlanControl()
                pc.type = imcpy.PlanControl.TypeEnum.REQUEST
                pc.op = imcpy.PlanControl.OperationEnum.START
                pc.plan_id = 'TestManeuver'
                pc.arg = spec

                self.send(self.estate, pc)
        else:
            logger.error('Unknown command')

    @RunOnce()
    async def aio_readline(self):
        try:
            while True:
                # TODO: this causes the stop() function to hang, as run_in_executor is not cancelled
                #       and waits for the next keyboard input before returning. Consider using
                #       the aioconsole package instead.
                rd = await self._loop.run_in_executor(None, sys.stdin.readline)
                for line in rd.splitlines():
                    self.on_console(line.strip())
        except RuntimeError:
            pass


if __name__ == '__main__':
    # Setup logging level and console output
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    # Create an actor, targeting the lauv-simulator-1 system
    actor = KeyboardActor('lauv-simulator-1')

    # This command starts the asyncio event loop
    actor.run()


