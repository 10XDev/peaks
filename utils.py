import numpy as np
from scipy.optimize import curve_fit
from matplotlib import pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy.interpolate import griddata
from sklearn.preprocessing import PolynomialFeatures
from sklearn import linear_model


def detrend(data, degree=1):
    '''
    Take 2D (i.e. image) data and remove the background using a polynomial fit

    Eventually this will be generalized to data of any dimension and perhaps

    Parameters
    ----------
    data : ndarray (NxM)
        data to detrend
    degree : int
        the degree of the polynomial with which to model the background

    Returns
    -------
    out : tuple of ndarrays (NxM)
        (data without background and background)
    '''

    x = np.arange(data.shape[1])
    y = np.arange(data.shape[0])
    xx, yy = np.meshgrid(x, y)

    # We have to take our 2D data and transform it into a list of 2D
    # coordinates
    X = np.dstack((xx.ravel(), yy.ravel())).reshape((np.prod(data.shape), 2))

    # We have to ravel our data so that it is a list of points
    vector = data.ravel()

    # now we can continue as before
    predict = X
    poly = PolynomialFeatures(degree)
    X_ = poly.fit_transform(X)
    predict_ = poly.fit_transform(predict)
    clf = linear_model.RANSACRegressor()

    # try the fit a few times, as it seems prone to failure
    ntries = 10
    for i in range(ntries):
        try:
            # try the fit
            clf.fit(X_, vector)
        except ValueError as e:
            # except the fit but do nothing
            # unless the number of tries has been reached
            if i == ntries-1:
                # then raise the error
                raise e
        else:
            # if no error is thrown, break out of the loop.
            break
    # we have to reshape our fit to mirror our original data
    background = clf.predict(predict_).reshape(data.shape)
    data_nb = data - background

    return data_nb, background


def nmoment(x, counts, c, n):
    '''
    A helper function to calculate moments of histograms
    '''
    return np.sum((x-c)**n*counts) / np.sum(counts)


def gauss_no_offset(x, amp, x0, sigma_x):
    '''
    Helper function to fit 1D Gaussians
    '''
    return amp*np.exp(-(x-x0)**2/(2*sigma_x**2))


def gauss(x, amp, x0, sigma_x, offset):
    '''
    Helper function to fit 1D Gaussians
    '''
    return amp*np.exp(-(x-x0)**2/(2*sigma_x**2))+offset


def gauss_fit(xdata, ydata, withoffset=True, trim=None, guess_z=None):
    offset = ydata.min()
    ydata_corr = ydata-offset

    if guess_z is None:
        x0 = nmoment(xdata, ydata_corr, 0, 1)
    else:
        x0 = guess_z

    sigma_x = np.sqrt(nmoment(xdata, ydata_corr, x0, 2))

    p0 = np.array([ydata_corr.max(), x0, sigma_x, offset])

    if trim is not None:
        args = abs(xdata-x0) < trim*sigma_x
        xdata = xdata[args]
        ydata = ydata[args]

    try:
        if withoffset:
            popt, pcov = curve_fit(gauss, xdata, ydata, p0=p0)
        else:
            popt, pcov = curve_fit(gauss_no_offset, xdata, ydata, p0=p0[:3])
            popt = np.insert(popt, 3, offset)
    except RuntimeError:
        popt = p0*np.nan

    return popt


def sine(x, amp, f, p, o):
    '''
    Utility function to fit nonlinearly
    '''
    return amp*np.sin(2*np.pi*f*x+p)+o


def grid(x, y, z, resX=1000, resY=1000, method='cubic'):
    "Convert 3 column data to matplotlib grid"
    if not np.isfinite(x+y+z).all():
        raise ValueError('x y or z is not finite')

    xi = np.linspace(x.min(), x.max(), resX)
    yi = np.linspace(y.min(), y.max(), resY)
    X, Y = np.meshgrid(xi, yi)
    Z = griddata((x, y), z, (X, Y), method=method)
    return X, Y, Z


def scatterplot(z, y, x, ax=None, fig=None, cmap='gnuplot2', **kwargs):
    '''
    A way to make a nice scatterplot with contours.
    '''

    if fig is None or ax is None:
        fig, ax = plt.subplots(1, 1, squeeze=True, figsize=(6, 6))

    # split out the key words for the grid method
    # so that the rest can be passed onto the first contourf call.
    grid_kwargs = {}
    for k in ('resX', 'resY', 'method'):
        try:
            grid_kwargs[k] = kwargs.pop(k)
        except KeyError:
            pass

    X, Y, Z = grid(x, y, z, **grid_kwargs)

    mymax = np.nanmax(z)
    mymin = np.nanmin(z)

    # conts=np.linspace(mymin, mymax, 20, endpoint=True)
    conts1 = np.linspace(mymin, mymax, 30)
    conts2 = np.linspace(mymin, mymax, 10)
    s = ax.contourf(X, Y, Z, conts1, origin='upper',
                    cmap=cmap, zorder=0, **kwargs)
    ax.contour(X, Y, Z, conts2, colors='k', origin='upper', zorder=1)

    # if there's more than 100 beads to fit then don't make spots
    if len(x) > 100:
        mark = '.'
    else:
        mark = 'o'

    ax.scatter(x, y, c='c', zorder=2, marker=mark)
    ax.invert_yaxis()
    the_divider = make_axes_locatable(ax)
    color_axis = the_divider.append_axes("right", size="5%", pad=0.1)
    plt.colorbar(s, cax=color_axis)
    return fig, ax
