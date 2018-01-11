"""
plasmapy.classes.simulation
============================

Classes and functionality for simulations.
"""

import numpy as np
import astropy.units as u
from ..numerical.spatial_solvers import Solver, shift
from ..constants import mu0


class MHDSimulation:
    r"""Physics class for magnetohydrodynamics.

    This class defines the MHD equations and implements time-stepping them:

    .. math::

       \frac{\partial \rho}{\partial t} + \nabla \cdot (\vec{v} \rho) = 0
       \frac{\partial (\rho \vec{v})}{\partial t} + \nabla \cdot (\vec{v} \rho \vec{v}) + \nabla p = 0
       \frac{\partial e}{\partial t} + \nabla \cdot (\vec{v} e + \vec{v} p) = 0

    for the fluid density, :math:`\rho`, momentum,
    :math:`\vec{m} = \vec{v} \rho`, energy :math:`e` and kinetic pressure
    :math:`p`. The pressure is a derived quantity defined as

    .. math::
       p = (\gamma - 1) (e - \frac{\rho \vec{v}^2}{2})

    Parameters
    ----------
    plasma : plasmapy.Plasma
        Plasma object describing variables that are being solved for, etc.
    gamma : float
        Value of the adiabatic index.

    Attributes
    ----------
    grid_size : tuple of ints
        Size of the simulation grid, as defined at initiation.
    gamma : float
        Adiabatic index for the simulation.
    """
    def __init__(self, plasma):
        """
        """
        self.dt = 1e-4 * u.s
        self.current_iteration = 0
        self.current_time = 0 * u.s
        self.plasma = plasma
        # Domain size
        # self.grid_size = grid_size

        # Physical parameters
        # self.gamma = gamma

        grids = (self.plasma.x.si, self.plasma.y.si, self.plasma.z.si)
        ranges = [grid for grid in grids if len(grid) > 1]
        stepsize = [range[1] - range[0] for range in ranges] * grids[0].unit
        self.solver = Solver(stepsize)

        # Collect equations into a nice easy-to-use list
        self.equations = [self._ddt_density, self._ddt_momentum,
                          self._ddt_energy, self._ddt_magfield]

    def time_stepper(self):
        """4th-order Runge-Kutta solver for stepping the simulation forward
        through time based on the equations defining the physics for the
        simulation.
        """
        half_dt = self.dt / 2
        kn = []
        derivs = []
        plasma = self.plasma
        orig_variables = [var.copy() for var in plasma.core_variables]

        for eq in self.equations:
            k1 = eq(self.current_time) * self.dt
            kn.append(k1)
            derivs.append(k1)
        for f, k1 in zip(plasma.core_variables, kn):
            np.add(f, k1/2, out=f)

        for i, (f, k1, eq) in enumerate(zip(plasma.core_variables, kn,
                                            self.equations)):
            k2 = eq(self.current_time + half_dt, f) * self.dt
            kn[i] = k2
            derivs[i] += (2 * k2)
        for f, f0, k2 in zip(plasma.core_variables, orig_variables, kn):
            np.add(f0, k2/2, out=f)

        for i, (f, k2, eq) in enumerate(zip(plasma.core_variables, kn,
                                            self.equations)):
            k3 = eq(self.current_time + half_dt, f) * self.dt
            kn[i] = k3
            derivs[i] += (2 * k3)
        for f, f0, k3 in zip(plasma.core_variables,
                             orig_variables, kn):
            np.add(f0, k3, out=f)

        for i, (f, k3, eq) in enumerate(zip(plasma.core_variables, kn,
                                            self.equations)):
            derivs[i] += eq(self.current_time+self.dt, f) * self.dt

        for f, f0, df in zip(plasma.core_variables,
                             orig_variables, derivs):
            np.add(f0, df/6, out=f)

        self.current_time += self.dt
        self.current_iteration += 1

    def _ddt_density(self, t, density=None):
        """
        """
        if not density:
            density = self.plasma.density
        nu = self.total_viscosity(self.plasma.density)
        D_rho = self.solver(nu, 0) * self.solver(self.plasma.density, 0)

        return D_rho - div(self.plasma.velocity * density, self.solver)

    def _ddt_momentum(self, t, momentum=None):
        """
        """
        if not momentum:
            momentum = self.plasma.momentum
        v = self.plasma.velocity
        B = self.plasma.magnetic_field / np.sqrt(mu0)

        D_mom = tensordiv(self.viscous_tensor, self.solver)

        return (D_mom - grad(self.plasma.pressure, self.solver)
                - tensordiv(vdp(v, momentum) - vdp(B, B), self.solver))

    def _ddt_energy(self, t, energy=None):
        """
        """
        if not energy:
            energy = self.plasma.energy
        v = self.plasma.velocity
        B = self.plasma.magnetic_field / np.sqrt(mu0)

        d_visc = div(vt_dot(v, self.viscous_tensor), self.solver)
        nu = self.total_viscosity(self.plasma.energy)
        d_diff = self.solver(nu, 0) * self.solver(self.plasma.energy, 0)
        # This should just be 0 for current testing purposes because there's
        # no B field
        # Therefore culling it for minor speed boost.
        # eps = self.epsilon
        # d_ohm = div(cross(B, eps), self.solver)

        D_e = d_diff + d_visc  # + d_ohm

        return D_e - div((v * energy)
                         - (B * dot(B, v))
                         + (v*self.plasma.pressure),
                         self.solver)

    def _ddt_magfield(self, t, magfield=None):
        """
        """
        if not magfield:
            B = self.plasma.magnetic_field / np.sqrt(mu0)
        else:
            B = magfield / np.sqrt(mu0)
        v = self.plasma.velocity

        return -tensordiv(vdp(v, B) - vdp(B, v), self.solver) * np.sqrt(mu0)

    @property
    def epsilon(self):
        """
        """

        nu = self.total_viscosity(self.plasma.magnetic_field/np.sqrt(mu0))

        eps = nu * self.solver(self.plasma.magnetic_field/np.sqrt(mu0), 0)
        return eps

    def shock_viscosity(self, paramaxis):
        """
        """

        c = 0.4
        dx = self.solver.dx[paramaxis]
        delv = div(self.plasma.velocity, self.solver)
        delv[np.where(delv > 0)] = 0

        return c * dx**2 * abs(delv)

    @property
    def viscous_tensor(self):
        r"""Defines the viscous tensor for the plasma following (approximately)
        Shelyag et al. 2008 (http://dx.doi.org/10.1051/0004-6361:200809800)
        """

        rho = self.plasma.density
        v = self.plasma.velocity
        visc = self.total_viscosity(v[0])
        # Define a new solver to differentiate individial velocity vectors.
        v_solver = Solver(self.solver.dx)

        # So very unsure about this equation right here
        visctens = np.zeros(shape=(3, 3, *self.plasma.domain_shape)) \
            * (u.m**2 / u.s**2)

        # This is fudged to work on the assumption that the tensor is symmetric
        visctens[0, 0] = (visc * v_solver(v[0], 0)) * 2
        visctens *= 0.5 * rho

        assert visctens.shape == (3, 3, *self.plasma.domain_shape), \
            """Viscous tensor calculated with incorrect shape: {}, should be {}
            """.format(visctens.shape, (3, 3, *self.grid_size))

        return visctens

    def hyperdiff_viscosity(self, param, paramaxis):
        """
        """

        vt = self.plasma.alfven_speed.max() + self.plasma.sound_speed.max()
        # solver_3rd_order = Solver(self.solver.dx, method='forward', deriv=3)
        # solver_1st_order = Solver(self.solver.dx, method='forward', deriv=1)
        # d3i_par = solver_3rd_order(param, paramaxis)
        # d1i_par = solver_1st_order(param, paramaxis)
        # # maxes_ratio = np.nanmax(d3i_par) / np.nanmax(d1i_par)
        # maxes_ratio = windowmax(d3i_par, paramaxis) / windowmax(d1i_par, paramaxis)
        # # print(maxes_ratio[np.isfinite(maxes_ratio)])
        # maxes_ratio[np.isnan(maxes_ratio)] = 0.0 * maxes_ratio.unit
        # maxes_ratio[np.isinf(maxes_ratio)] = 0.0 * maxes_ratio.unit
        # print(np.isnan(maxes_ratio).any())
        # if param is self.plasma.energy or param is self.plasma.density:
        #     c = 0.04 * u.m**2
        # else:
        #     c = 0.4 * u.m**2
        # print('===', c, self.solver.dx[paramaxis], vt.si)
        c = 1 #* u.m **2
        visc = c * self.solver.dx[paramaxis] * vt #* maxes_ratio
        # print(param.max(), d3i_par.max(), d1i_par.max(), maxes_ratio)
        return visc

    def total_viscosity(self, param, paramaxis=0):
        """
        """

        return self.hyperdiff_viscosity(param, paramaxis) \
             + self.shock_viscosity(paramaxis)


def dot(vec1, vec2):
    r"""Calculates the dot product of two arrays of vector quantities.
    TODO: Replace this everywhere with the new NumPy way of doing this.

    Parameters
    ----------

    vec1, vec2 : array-like, shape=(3, x, [y, z])
        Arrays of vector values in a 1D, 2D or 3D domain.

    Returns
    -------

    scalar : numpy.ndarray, shape=(x, [y, z])
        3D grid of scalar values which are the dot products of specified
        vectors,

        .. math::

           a = \vec{v_1} \cdot \vec{v_2}
    """

    assert vec1.shape[0] == 3, "First argument provided is not a vector field"
    assert vec2.shape[0] == 3, "Second argument provided is not a vector field"
    assert vec1.shape == vec2.shape, """
        Shapes of vectors provided do not match: {}/{}
        """.format(vec1.shape, vec2.shape)

    product = np.sum(vec1 * vec2, axis=0)
    assert product.shape == vec1.shape[1:], """
        Result calculated has shape {}, should be {}
        """.format(product.shape, vec1.shape[1:])

    return product


def cross(vec1, vec2):
    r"""Calculates the cross product of two arrays of vector quantities.

    Parameters
    ----------

    vec1, vec2 : array-like, shape=(3, x, [y, z])
        Arrays of vector values in a 1D, 2D or 3D domain.

    Returns
    -------

    product : numpy.ndarray, shape=(3, x, [y, z])
        Vector field corresponding to the cross product of the specified
        vectors,

        .. math::

           \vec{a} = \vec{v_1} \times \vec{v_2}
    """

    assert vec1.shape[0] == 3, "First argument provided is not a vector field"
    assert vec2.shape[0] == 3, "Second argument provided is not a vector field"
    assert vec1.shape == vec2.shape, """
        Shapes of vectors provided do not match: {}/{}
        """.format(vec1.shape, vec2.shape)

    product = np.array((((vec1[1] * vec2[2]) - (vec1[2] * vec2[1])),
                        ((vec1[2] * vec2[0]) - (vec1[0] * vec2[2])),
                        ((vec1[0] * vec2[1]) - (vec1[1] * vec2[0]))))\
        * vec1.unit * vec2.unit
    assert product.shape == vec1.shape, """
        Result calculated has shape {}, should be {}
        """.format(product.shape, vec1.shape)

    return product


def grad(f, solver):
    r"""Calculates the gradient of a scalar field.

    Parameters
    ----------

    f : array-like, shape=(x, [y, z])
        1-, 2- or 3-dimensional scalar field.

    Returns
    -------

    gradient : astropy.units.Quantity, shape=(3, x, [y, z])
        Vector field corresponding to the gradient of the specified scalar
        field,

        .. math::

           \vec{a} = \nabla f
    """

    assert len(solver.dx) == len(f.shape), """
        Number of grid step sizes ({}) != to dimensionality of field ({})
        """.format(len(h), len(f.shape))

    gradient = np.zeros((3, *f.shape)) * f.unit / solver.dx.unit
    for dim in range(len(solver.dx)):
        gradient[dim] = solver(f, dim)

    return gradient


def div(vec, solver):
    r"""Calculates the divergence of a vector field.

    Parameters
    ----------

    vec : array-like, shape=(3, x, [y, z])
        3-dimensional vector field.

    Returns
    -------

    divergence : numpy.ndarray, shape=(x, [y, z])
        Scalar field of values corresponding to divergence of specified vector
        field,

        .. math::

           a = \nabla \cdot \vec{v}
    """

    assert vec.shape[0] == 3, "First argument provided is not a vector field"
    assert len(solver.dx) == len(vec.shape[1:]), """
        Number of grid step sizes ({}) != to dimensionality of field ({})
        """.format(len(solver.dx), len(vec.shape[1:]))

    dims = range(len(solver.dx))
    divergence = sum([solver(vec[i], i) for i in dims])
    assert divergence.shape == vec.shape[1:], """
        Output field has shape {}, should be {}
        """.format(divergence.shape, vec.shape[1:])

    return divergence


def vdp(vec1, vec2):
    r"""Calculate the Vector Direct Product of two vectors.

    Parameters
    ----------

    vec1, vec2 : array-like, shape=(3, x, [y, z])
        Arrays of vector values in a 1D, 2D or 3D domain.

    Returns
    -------

    tensor : numpy.ndarray, shape=(3, 3, x, [y, z])
        Tensor field resulting from direct product of the specified vectors.

        .. math::

           \textbf{A} = \vec{v_1} \vec{v_2}

    References
    ----------
    http://mathworld.wolfram.com/VectorDirectProduct.html

    """

    assert vec1.shape[0] == 3, "First argument provided is not a vector field"
    assert vec2.shape[0] == 3, "Second argument provided is not a vector field"
    assert vec1.shape == vec2.shape, """
        Shapes of vectors provided do not match: {}/{}
        """.format(vec1.shape, vec2.shape)

    tensor = vec1 * vec2.reshape(3, 1, *vec2.shape[1:])
    assert tensor.shape == (3, *vec1.shape), """
        Output field has shape {}, should be {}
        """.format(tensor.shape, (3, *vec1.shape))

    return tensor


def tensordiv(tensor, solver):
    r"""Calculates the divergence of a tensor field.

    Parameters
    ----------

    tensor : array-like, shape=(3, 3, x, [y, z])
        3-dimensional tensor field.

    Returns
    -------

    divergence : numpy.ndarray, shape=(3, x, [y, z])
        Vector field corresponding to the divergence of the input tensor field.

        .. math::

           \vec{a} = \nabla \cdot \textbf{T}
    """

    assert tensor.shape[:2] == (3, 3), """
        First argument provided is not a tensor field"""
    assert len(solver.dx) == len(tensor.shape[2:]), """
        Number of grid step sizes ({}) != to dimensionality of field ({})
        """.format(len(solver.dx), len(tensor.shape[2:]))

    dims = range(len(solver.dx))
    divergence = np.array([sum([solver(tensor[i, 0, ...], i) for i in dims]),
                           sum([solver(tensor[i, 1, ...], i) for i in dims]),
                           sum([solver(tensor[i, 2, ...], i) for i in dims])])\
        * tensor.unit / solver.dx.unit
    assert divergence.shape == tensor.shape[1:], """
        Output field has shape {}, should be {}
        """.format(divergence.shape, tensor.shape[1:])

    return divergence


def vt_dot(vec, tensor):
    r"""Calculate the dot product of a vector with a tensor.

    Parameters
    ----------
    vec : array-like, shape=(3, x, [y, z])
        Array of vector values in a 1D, 2D or 3D domain.

    tensor : array-like, shape=(3, 3, x, [y, z])
        Tensor field in the same space as the vector above.

    Returns
    -------
    dot : ndarray, shape=(3, x, [y, z])
        Resultant vector field.
    """

    assert vec.shape[0] == 3, "First argument provided is not a vector field"
    assert tensor.shape[:2] == (3, 3), \
        "Second argument provided is not a tensor field"

    dims = range(len(vec.shape[1:]))
    dot = np.array([sum([vec[i] * tensor[i, 0, ...] for i in dims]),
                    sum([vec[i] * tensor[i, 1, ...] for i in dims]),
                    sum([vec[i] * tensor[i, 2, ...] for i in dims])]) \
        * vec.unit * tensor.unit
    assert dot.shape == tensor.shape[1:], \
        "Output field has shape {}, should be {}".format(dot.shape,
                                                         tensor.shape[1:])

    return dot


def windowmax(f, axis):
    r"""Find the maximum of the given array over a 5-point window for each
    point in the grid.

    Parameters
    ----------

    f : Parameter
        Array of values for which to find the 5-window maximum.

    axis : int [0 | 1 | 2]
        Direction in which to calculate the maxima. 0, 1, and 2 correspond to
        the x, y and z axes, respectively.
    """

    padding = [(0, 0)] * len(f.shape)
    padding[axis] = (4, 4)
    f = abs(np.pad(f.si, padding, 'edge')) * f.unit
    maxvals = np.array([f[shift(f.shape, i, axis)]
                        for i in range(-1, 2)]).max(axis=0)

    return maxvals * f.unit
