#A module for generating and fitting 2D gaussian data

#numpy for numerical
import numpy as np
#need measure to take image moments
from skimage.measure import moments, moments_central
#need basic curve fitting
from scipy.optimize import curve_fit

import warnings
from scipy.optimize import OptimizeWarning

#Eventually we'll want to abstract the useful, abstract bits of this class to a
#parent class called peak that will allow for multiple types of fits
class Gauss2D(object):
    """
    A class that encapsulates experimental data that is best modeled by a 2D
    gaussian peak. It can estimate model parameters and perform a fit to the
    data. Best fit parameters are stored in a dictionary that can be accessed
    by helper functions.

    Right now the class assumes that `data` has constant spacing
    """
    def __init__(self, data):
        '''
        Holds experimental equi-spaced 2D-data best represented by a Gaussian

        Parameters
        ----------
        data : array_like
            An array holding the experimental data, for now data is assumed to
            have equal spacing

        Returns
        -------
        out : object
            A Gauss2D object holding the specified data. All other internal
            variables are internalized to `None`
        '''

        #Note that we are only passing a reference to the original data here
        #so DO NOT modify this field
        self._data = data
        self._guess_params = None
        self._opt_params = None
        self._angle = None

    #################################
    #   STATIC METHOD DEFINITIONS   #
    #################################
    @classmethod
    def gauss2D(cls, xdata_tuple, amp, mu0, mu1, sigma0, sigma1, rho, offset):
        '''
        A model function for a bivariate normal distribution (not normalized)

        see http://mathworld.wolfram.com/BivariateNormalDistribution.html for
        details

        Parameters
        ----------
        xdata_tuple : tuple of array_like objects
            First element is x0 and second is x1, each usually from np.meshgrid
            x0 and x1 must have the same shape
        amp : float
            Amplitude
        mu0 : float
            center x position
        mu1 : float
            center y position
        sigma0 : float
            x width
        sigma1 : float
            y width
        rho : float
            correlation between x and y (defines the angle the distributions
            major axes make with the coordinate system)
        offset : float
            offset

        Returns
        -------
        g : array_like
            A matrix of values that represent a 2D Gaussian peak. `g` will have
            the same dimensions as `x0` and `x1`
        '''

        (x0, x1) = xdata_tuple

        if x0.shape != x1.shape:
            #All functions assume that data is 2D
            raise ValueError

        z =((x0-mu0)/sigma0)**2 - 2*rho*(x0-mu0)*(x1-mu1)/(sigma0*sigma1) + ((x1-mu1)/sigma1)**2

        g = offset + amp*np.exp( -z/(2*(1-rho**2)))
        return g

    @classmethod
    def gauss2D_norot(cls, xdata_tuple, amp, x0, y0, sigma_x, sigma_y, offset):
        '''
        A special case of gauss2D with rho = 0
        '''

        #return the general form with a rho of 0
        return cls.gauss2D(xdata_tuple, amp, x0, y0, sigma_x, sigma_y, 0.0, offset)

    @classmethod
    def gauss2D_sym(cls, xdata_tuple, amp, x0, y0, sigma_x, offset):
        '''
        A special case of gauss2D_norot with sigma_x = sigma_y
        '''

        #return the no rotation form with same sigmas
        return cls.gauss2D_norot(xdata_tuple, amp, x0, y0, sigma_x, sigma_x, offset)

    @classmethod
    def model(cls, xdata_tuple, *args):
        '''
        Chooses the correct model function to use based on the number of
        arguments passed to it

        Parameters
        ----------
        xdata_tuple : tuple of ndarrays (xx, yy)
            The independent data

        Returns
        -------
        modeldata :

        Other Parameters
        ----------------
        *args : model parameters
        '''
        num_args = len(args)

        if num_args == 5:
            return cls.gauss2D_sym(xdata_tuple, *args)
        elif num_args == 6:
            return cls.gauss2D_norot(xdata_tuple, *args)
        elif num_args == 7:
            return cls.gauss2D(xdata_tuple, *args)
        else:
            raise ValueError

        #return something in case everything is really fucked
        return -1 #should NEVER see this

    def optimize_params_ls(self, guess_params = None, modeltype = 'full'):
        '''
        A function that will optimize the parameters for a 2D Gaussian model
        using a least squares method

        Parameters
        ----------
        self : array_like

        Returns
        -------

        Notes
        -----
        This function will call scipy.optimize to optimize the parameters of
        the model function
        '''

        #Test if we've been provided guess parameters
        if guess_params is None:
            #if not we generate them
            guess_params = self.estimate_params()
            if modeltype.lower() == 'sym':
                guess_params = np.delete(guess_params,5)
            elif modeltype.lower() == 'norot':
                guess_params = np.delete(guess_params,(4,5))
        #if yes we save them to the object for later use
        else:
            self._guess_params = guess_params

        #pull the data attribute for use
        data = self._data

        #We need to generate the x an y coordinates for the fit

        #remember that image data generally has the higher dimension first
        #as do most python objects
        y = np.arange(data.shape[0])
        x = np.arange(data.shape[1])
        xx, yy = np.meshgrid(x,y)

        #define our function for fitting
        def model_ravel(*args) : return self.model(*args).ravel()

        #Here we fit the data but we catch any errors and instead set the
        #optimized parameters to zero.
        with warnings.catch_warnings():
            warnings.simplefilter("error", OptimizeWarning)
            try:
                popt, pcov = curve_fit(model_ravel, (xx, yy), data.ravel(), p0=guess_params)
            except (OptimizeWarning, ValueError, RuntimeError):
                popt = np.zeros_like(guess_params)
            else:
                max_s = max(data.shape)
                if len(popt) < 6:
                    if popt[3] > max_s:
                        popt = np.zeros_like(guess_params)
                else:
                    if popt[3] > max_s or popt[4] > max_s:
                        popt = np.zeros_like(guess_params)

        #save parameters for later use
        self._opt_params = popt

        #return copy to user
        return popt.copy()

    def estimate_params(self):
        '''
        Estimate the parameters that best model the data using it's moments

        Returns
        -------
        params : array_like
            params[0] = amp
            params[1] = x0
            params[2] = y0
            params[3] = sigma_x
            params[4] = sigma_y
            params[5] = rho
            params[6] = offset

        Notes
        -----
        This method works _very_ poorly if the data has any bias
        '''

        #initialize the array
        params = np.zeros(7)

        #pull data from the object for easier use
        data = self._data

        #calculate the moments up to second order
        M = moments(data, 2)

        #calculate model parameters from the moments
        #https://en.wikipedia.org/wiki/Image_moment#Central_moments
        xbar = M[1,0]/M[0,0]
        ybar = M[0,1]/M[0,0]
        xvar = M[2,0]/M[0,0]-xbar**2
        yvar = M[0,2]/M[0,0]-ybar**2
        covar = M[1,1]/M[0,0]-xbar*ybar

        #place the model parameters in the return array
        params[:3] = data.max(), xbar, ybar
        params[3] = np.sqrt(np.abs(xvar))
        params[4] = np.sqrt(np.abs(yvar))
        params[5] = covar/np.sqrt(np.abs(xvar*yvar))
        params[6] = data.min()

        #save estimate for later use
        self._guess_params = params

        #return parameters to the caller as a `copy`, we don't want them to
        #change the internal state
        return params.copy()

    def get_guess_params(self):
        '''
        Returns a copy of _guess_params so that user doesn't unwittingly change
        internal state

        Returns
        -------
        guess_params : array_like
            A copy of the objects internal estimated parameters for the model
        '''
        return self._guess_params.copy()

    def get_opt_params(self):
        '''
        Returns a copy of _opt_params so that user doesn't unwittingly change
        internal state

        Returns
        -------
        guess_params : array_like
            A copy of the objects internal estimated parameters for the model
        '''
        return self._opt_params.copy()

    def optimize_params_mle(self):
        print('This function has not been implemented yet, passing to\
                optimize_params_ls.')
        return optimize_params_ls(self)

    def plot_estimated(self):
        raise NotImplementedError('plot_estimated(self)')

    def plot_optimized(self):
        raise NotImplementedError('plot_optimized(self)')

    def plot(self):
        raise NotImplementedError('plot(self)')

    def _subplot(self):
        raise NotImplementedError('_subplot(self)')

if __name__ == '__main__':
    pass
    # def model_function_test():
    #     # Create x and y indices
    #     x = np.arange(64)
    #     y = np.arange(128)
    #     x, y = np.meshgrid(x, y)
    #
    #     #create data
    #     testdata = Gauss2D().gauss2D((x, y), 3, 32, 32, 5, 10, 10)
    #
    #     # add some noise to the data and instantiate object with noisy data
    #     my_gauss = Gauss2D(testdata + 0.2*np.random.randn(*testdata.shape))
    #     initial_guess = zeros(6)
    #
    #     initial_guess = my_gauss.estimate_params()
    #
    #     print(initial_guess)
    #
    #     initial_guess2d = gaussian2D((x, y), *initial_guess)
    #
    #     fig, ax = plt.subplots(1, 1)
    #     ax.hold(True)
    #     ax.matshow(testdata_noisy, origin='bottom', extent=(x.min(), x.max(), y.min(), y.max()))
    #     ax.contour(x, y, initial_guess2d, 8, colors='r')
    #
    #     popt, pcov = curve_fit(gaussian2D_fit, (x, y), testdata_noisy.ravel(), p0=initial_guess)
    #
    #     #And plot the results:
    #
    #     testdata_fitted = gaussian2D((x, y), *popt)
    #
    #     fig, ax = plt.subplots(1, 1)
    #     ax.hold(True)
    #     ax.matshow(testdata_noisy, origin='bottom', extent=(x.min(), x.max(), y.min(), y.max()))
    #     ax.contour(x, y, testdata_fitted, 8, colors='r')
