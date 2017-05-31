"""
plasmapy.classes.simulation
============================

Classes and functionality for simulations.
"""

import numpy as np
import astropy.units as u
from ..constants import mu0


class MHDSimulation():
    """Physics class for magnetohydrodynamics.

    This class defines the MHD equations and implements time-stepping them:

    .. math::

       \\frac{\\partial \\rho}{\\partial t} + \\nabla \\cdot (\\vec{v} \\rho) = 0
       \\frac{\\partial (\\rho \vec{v})}{\\partial t} + \\nabla \\cdot (\\vec{v} \\rho \\vec{v}) + \\nabla p = 0
       \\frac{\\partial e}{\\partial t} + \\nabla \\cdot (\\vec{v} e + \\vec{v} p) = 0

    for the fluid density, :math:`\\rho`, momentum, :math:`\\vec{m} = \\vec{v} \\rho`, energy :math:`e` and kinetic pressure :math:`p`.
    The pressure is a derived quantity defined as

    .. math::
       p = (\\gamma - 1) (e - \\frac{\\rho \\vec{v}^2}{2})

    Parameters
    ----------
    grid_size : tuple of ints
        Tuple of 1, 2 or 3 values defining the size of the simulation grid.
    gamma : float
        Value of the adiabatic index.

    Attributes
    ----------
    grid_size : tuple of ints
        Size of the simulation grid, as defined at initiation.
    gamma : float
        Adiabatic index for the simulation.
    """
    def __init__(self):  #, grid_size, gamma=5/3):
        """
        """
        self.dt = 0
        self.current_iteration = 0
        self.current_time = 0 * u.s
        # Domain size
        # self.grid_size = grid_size

        # Physical parameters
        # self.gamma = gamma

        # Collect equations into a nice easy-to-use list
        # self.equations = [self._ddt_density, self._ddt_momentum,
        #                  self._ddt_energy, self._ddt_magfield]

    def time_stepper(self):
        pass

    def _ddt_density(self, t, density=None):
        """
        """
        if not density:
            density = self.density
        return -div(self.velocity * density, self.solver)

    def _ddt_momentum(self, t, momentum=None):
        """
        """
        if not momentum:
            momentum = self.momentum
        v = self.velocity
        B = self.magnetic_field / np.sqrt(mu0)

        return (-grad(self.pressure, self.solver) \
                - tensordiv(vdp(v, momentum) - vdp(B, B), self.solver))

    def _ddt_energy(self, t, energy=None):
        """
        """
        if not energy:
            energy = self.energy
        v = self.velocity
        B = self.magnetic_field / np.sqrt(mu0)

        return -div((v*energy) - (B * dot(B, v)) + (v*self.pressure), self.solver)

    def _ddt_magfield(self, t, magfield=None):
        """
        """
        if not magfield:
            B = self.magnetic_field / np.sqrt(mu0)
        else:
            B = magfield / np.sqrt(mu0)
        v = self.velocity

        return -tensordiv(vdp(v, B) - vdp(B, v), self.solver) * np.sqrt(mu0)


def dot(vec1, vec2):
    """
    Calculates the dot product of two arrays of vector quantities.
    TODO: Replace this everywhere with the new NumPy way of doing this.

    Parameters
    ----------

    vec1, vec2 : array-like, shape=(3, x, [y, z])
        Arrays of vector values in a 1D, 2D or 3D domain.

    Returns
    -------

    scalar : ndarray, shape=(x, [y, z])
        3D grid of scalar values which are the dot products of specified
        vectors,

        .. math::

           a = \\vec{v_1} \\cdot \\vec{v_2}

    """

    assert vec1.shape[0] == 3, "First argument provided is not a vector field"
    assert vec2.shape[0] == 3, "Second argument provided is not a vector field"
    assert vec1.shape == vec2.shape, \
        "Shapes of vectors provided do not match: {}/{}".format(vec1.shape,
                                                                vec2.shape)

    product = np.sum(vec1 * vec2, axis=0)
    assert product.shape == vec1.shape[1:], \
        "Result calculated has shape {}, should be {}".format(product.shape,
                                                              vec1.shape[1:])

    return product

