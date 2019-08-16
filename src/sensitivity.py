# Built-in modules
import numpy as np
import warnings as wn
import functools as ft

# BoloCalc modules
import src.unit as un
import src.distrib as ds


class Sensitivity:
    def __init__(self, sim):
        # Store passed parameters
        self.exp = sim.exp
        self._log = sim.log
        self._phys = sim.phys
        self._noise = sim.noise
        self._corr = sim.param("corr")
        self._nobs = sim.param("nobs")
        self._ndet = sim.param("ndet")

    # ***** Public Methods *****
    def sensitivity(self, exp=None):
        '''
        if tel is not None and cam is not None and ch is not None:
            channel = self._exp.tels[tel].cams[cam].chs[ch]
            self.sens[tel][cam][ch] = self._sensitivity(chan)
        elif tel is not None and cam is not None and ch is None:
            for ch, channel in self._exp.tels[tel].cams[cam].chs.items():
                self.sens[tel][cam][ch] = self._sensitivity(channel)
        elif tel is not None and cam is None and ch is None:
            for cam, camera in self._exp.tels[tel].cams:
                for ch, channel in camera.chs:
                    self.sens[tel][cam][ch] = self._sensitivity(channel)
        else:  # (Re)generate entire dictionary
            self.sens = {tp_name: {cm_name: {ch_name: self._sensitivity(ch)
                                             for (ch_name, ch)
                                             in cm.chs.items()}
                                   for (cm_name, cm)
                                   in tp.cams.items()}
                         for (tp_name, tp)
                         in self.exp.tels.items()}
        return self.sens
        '''
        if exp is None:
            exp = self.exp
        return [[[self._sensitivity(ch) for ch in cam.chs]
                for cam in tp.cams]
                for tp in exp.tels]

    def opt_pow(self, spec=None):
        '''
        self.opt_pow = {tp_name: {cm_name: {ch_name: self._opt_pow(ch)
                                            for (ch_name, ch)
                                            in cm.chs.items()}
                                  for (cm_name, cm)
                                  in tp.cams.items()}
                        for (tp_name, tp)
                        in self.exp.tels.items()}
        '''
        return [[[self._opt_pow(ch) for ch in cm.chs]
                for cm in tp.cams]
                for tp in self._exp.tels]

    # ***** Helper Methods *****
    def _sensitivity(self, ch):
        # Calculate optical power
        self._calc_popt(ch)
        self._calc_rj_temp(ch)
        # Calculate NEP
        self._calc_photon_NEP(ch)
        self._calc_bolo_NEP(ch)
        self._calc_read_NEP(ch)
        self._calc_tot_NEP(ch)
        # Calculte NET
        self._calc_NET(ch)
        self._calc_NET_RJ(ch)
        # Calculate array NET
        self._calc_NET_arr(ch)
        self._calc_NET_arr_RJ(ch)
        # Calculate correlation degradation
        self._calc_corr_deg(ch)
        # Calculate map depth
        self._calc_map_depth(ch)
        self._calc_map_depth_RJ(ch)

        # Return a list of parameter distributions
        return [self._tel_eff_arr.flatten().tolist(),
                self._popt_arr.flatten().tolist(),
                self._tel_rj_temp.flatten().tolist(),
                self._sky_rj_temp.flatten().tolist(),
                self._NEP_ph_arr.flatten().tolist(),
                self._NEP_bolo_arr.flatten().tolist(),
                self._NEP_read_arr.flatten().tolist(),
                self._NEP.flatten().tolist(),
                self._NET.flatten().tolist(),
                self._NET_RJ.flatten().tolist(),
                self._NET_arr.flatten().tolist(),
                self._NET_arr_RJ.flatten().tolist(),
                self._corr_deg.flatten().tolist(),
                self._map_depth.flatten().lolist(),
                self._map_depth_RJ.flatten().tolist()]

    def _opt_pow(self, ch):
        # Store passed parameters
        tp = ch.cam.tel
        self._pow_sky_side = []
        self._pow_det_side = []
        self._eff_det_side = []
        for i in range(len(ch.elem)):  # nobs
            pow_sky_side_1 = []
            pow_det_side_1 = []
            eff_det_side_1 = []
            for j in range(len(ch.elem[i])):  # ndet
                pows = []
                pow_sky_side_2 = []
                pow_det_side_2 = []
                eff_sky_side_2 = []
                eff_det_side_2 = []
                # Store efficiency towards sky and towards detector
                for k in range(len(ch.elem[i][j])):  # nelem
                    # Buffer the efficiency array
                    eff_arr = np.vstack([ch.tran[i][j],
                                         np.array([1. for f in ch.freqs])])
                    # Efficiency towards the detector
                    cum_eff_det = ft.reduce(lambda x, y: x*y, eff_arr[k+1:])
                    eff_det_side_2.append(np.array(cum_eff_det))
                    # Efficiency towards the sky
                    if k == 0:
                        # Zero elements sky side
                        cum_eff_sky = [[0. for f in ch.freqs]]
                    elif k == 1:
                        # One element sky side
                        cum_eff_sky = [[1. for f in ch.freqs],
                                       [0. for f in ch.freqs]]
                    else:
                        cum_eff_sky = [ft.reduce(
                            lambda x, y: x*y, eff_arr[m+1:k])
                            if m < k-2 else eff_arr[m+1]
                            for m in range(k-1)] + [[1. for f in ch.freqs],
                                                    [0. for f in ch.freqs]]
                    eff_sky_side_2.append(cum_eff_sky)
                    pow = self._phys.bb_pow_spec(
                        ch.freqs, ch.temp[i][j][k], ch.emis[i][j][k])
                    pows.append(pow)
                # Store power from sky and power on detector
                for k in range(len(ch.elem[i][j])):
                    pow_out = np.trapz(
                        pows[k] * eff_det_side_2[k] * ch.band_mask, ch.freqs)
                    eff_det_side_2[k] = np.trapz(
                        eff_det_side_2[k] * ch.band_mask, ch.freqs) / (
                            float(ch.freqs[-1] - ch.freqs[0]))
                    pow_det_side_2.append(pow_out)
                    pow_in = sum([np.trapz(
                        pows[m] * eff_sky_side_2[k][m] *
                        ch.band_mask, ch.freqs)
                        for m in range(k+1)])
                    pow_sky_side_2.append(pow_in)
                pow_sky_side_1.append(pow_sky_side_2)
                pow_det_side_1.append(pow_det_side_2)
                eff_det_side_1.append(eff_det_side_2)
            self._pow_sky_side.append(pow_sky_side_1)
            self._pow_det_side.append(pow_det_side_1)
            self._eff_det_side.append(eff_det_side_1)
        # Build table of optical powers and efficiencies for each element
        return self._opt_table()

    def _calc_popt(self, ch):
        self._popt_arr = np.array([[self._popt(
            ch.elem[i][j], ch.emis[i][j], ch.tran[i][j],
            ch.temp[i][j], ch.freqs)
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        return

    def _calc_rj_temp(self, ch):
        # Calculate experiment RJ temperature
        n_sky_elem = self._num_sky_elem(ch)
        self._tel_eff_arr = np.array([[self._eff(
            ch.tran[i][j][n_sky_elem:],
            ch.freqs)
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        self._tel_rj_temp = np.array([[self._rj_temp(
            ch.elem[i][j][n_sky_elem:],
            ch.emis[i][j][n_sky_elem:],
            ch.tran[i][j][n_sky_elem:],
            ch.temp[i][j][n_sky_elem:],
            ch.freqs, self._tel_eff_arr[i][j])
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        self._sky_rj_temp = np.array([[self._rj_temp(
            ch.elem[i][j][:n_sky_elem],
            ch.emis[i][j][:n_sky_elem],
            ch.tran[i][j],
            ch.temp[i][j][:n_sky_elem],
            ch.freqs, self._tel_eff_arr[i][j])
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        return

    def _calc_photon_NEP(self, ch):
        if self._corr:
            pass_ch = ch
        else:
            pass_ch = None
        NEP_ph_arr = np.array([[self._photon_NEP(
            ch.elem[i][j], ch.emis[i][j], ch.tran[i][j],
            ch.temp[i][j], ch.freqs, pass_ch)
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        NEP_ph_arr, NEP_ph_arr_corr = np.split(NEP_ph_arr, 2, axis=2)
        self._NEP_ph_arr = np.reshape(
            NEP_ph_arr, np.shape(NEP_ph_arr)[:2])
        self._NEP_ph_arr_corr = np.reshape(
            NEP_ph_arr_corr, np.shape(NEP_ph_arr_corr)[:2])
        return

    def _calc_bolo_NEP(self, ch):
        self._NEP_bolo_arr = np.array([[self._bolo_NEP(
            self._popt_arr[i][j], ch.det_arr.dets[j])
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        return

    def _calc_read_NEP(self, ch):
        NEP_read_arr = np.array([[self._read_NEP(
            self._popt_arr[i][j], ch.det_arr.dets[j])
            for j in range(self._ndet)]
            for i in range(self._nobs)])

        if np.any(np.isin(NEP_read_arr, ['NA'])):
            self._NEP_read_arr = np.array([[np.sqrt(
                (1. + ch.det_arr.dets[j].param("read_frac"))**2 - 1.) *
                np.sqrt(self._NEP_ph_arr[i][j]**2 +
                        self._NEP_bolo_arr[i][j]**2)
                for j in range(self._ndet)]
                for i in range(self._nobs)])
        else:
            self._NEP_read_arr = NEP_read_arr
        return

    def _calc_tot_NEP(self, ch):
        self._NEP = np.sqrt(self._NEP_ph_arr**2 +
                            self._NEP_bolo_arr**2 +
                            self._NEP_read_arr**2)
        # Total NEP with correlation adjustment
        self._NEP_corr = np.sqrt(self._NEP_ph_arr_corr**2 +
                                 self._NEP_bolo_arr**2 +
                                 self._NEP_read_arr**2)
        return

    def _calc_NET(self, ch):
        # Total NET
        self._NET = np.array([[self._noise.NET_from_NEP(
            self._NEP[i][j], ch.freqs, np.prod(ch.tran[i][j], axis=0),
            ch.cam.param("opt_coup"))
            for j in range(self._ndet)]
            for i in range(self._nobs)]) * (
                ch.cam.tel.param("net_mgn"))
        # Total NET with correlation adjustment
        self._NET_corr = np.array([[self._noise.NET_from_NEP(
            self._NEP_corr[i][j], ch.freqs, np.prod(ch.tran[i][j], axis=0),
            ch.cam.param("opt_coup"))
            for j in range(self._ndet)]
            for i in range(self._nobs)]) * (
                ch.cam.tel.param("net_mgn"))
        return

    def _calc_NET_RJ(self, ch):
        self._NET_RJ = np.array([[self._Trj_over_Tcmb(
            ch.freqs)*self._NET[i][j]
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        self._NET_corr_RJ = np.array([[self._Trj_over_Tcmb(
            ch.freqs)*self._NET_corr[i][j]
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        return

    def _calc_NET_arr(self, ch):
        self._NET_arr = np.array([[self._noise.NET_arr(
            self._NET_corr[i][j], ch.param("ndet"), ch.param("yield"))
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        return

    def _calc_NET_arr_RJ(self, ch):
        self._NET_arr = np.array([[self._noise.NET_arr(
            self._NET_corr_RJ[i][j], ch.param("ndet"), ch.param("yield"))
            for j in range(self._ndet)]
            for i in range(self._nobs)])
        return

    def _calc_corr_deg(self, ch):
        self._corr_deg = np.array([[self._NET_corr[i][j] / self._NET[i][i]
                                  for i in range(self._ndet)]
                                  for i in range(self._nobs)])
        return

    def _calc_map_depth(self, ch):
        self._map_depth = np.array([[self._noise.map_depth(
            self._NET_arr, tel.param("fsky"),
            tel.param("tobs"), tel.param("obs_eff"))
            for i in range(self._ndet)]
            for j in range(self._nobs)])
        return

    def _calc_map_depth_RJ(self, ch):
        self._map_depth_RJ = np.array([[self._noise.map_depth(
            self._NET_arr_RJ, tel.param("fsky"),
            tel.param("tobs"), tel.param("obs_eff"))
            for i in range(self._ndet)]
            for j in range(self._nobs)])
        return

    def _eff(self, tran, freqs):
        tran = self._buffer_tran(tran, freqs)
        bw = freqs[-1] - freqs[0]
        tot_eff = np.trapz(np.prod(tran, axis=0), freqs)/bw
        return tot_eff

    def _popt(self, elem, emis, tran, temp, freqs):
        tran = self._buffer_tran(tran, freqs)
        tot_pow = np.sum([np.trapz(
            self._phys.bb_pow_spec(
                freqs, temp[i], emis[i] *
                np.prod(tran[i+1:], axis=0)), freqs)
                for i in range(len(elem))])
        return tot_pow

    def _rj_temp(self, elem, emis, tran, temp, freqs, eff):
        opt_pow = self._popt(elem, emis, tran, temp, freqs)
        bw = freqs[-1] - freqs[0]
        rj_temp = self._phys.rj_temp(opt_pow, bw, eff)
        return rj_temp

    def _photon_NEP(self, elem, emis, tran, temp, freqs, ch=None):
        tran = self._buffer_tran(tran, freqs)
        if ch:
            corrs = True
        else:
            corrs = False
        pow_ints = np.array([self._phys.bb_pow_spec(
            freqs, temp[i], emis[i]*np.prod(tran[i+1:], axis=0))
            for i in range(len(elem))])
        if corrs:
            # Photon NEP both without and with correlations
            NEP_ph, NEP_ph_arr = self._noise.photon_NEP(
                pow_ints, freqs, elem, (
                    ch.param("pix_sz") /
                    float(ch.cam.param("fnum") * self._phys.lamb(
                        ch.param("bc")))))
        else:
            # Both outputs are identical
            NEP_ph, NEP_ph_arr = self._noise.photon_NEP(pow_ints, freqs)
        return NEP_ph, NEP_ph_arr

    def _bolo_NEP(self, opt_pow, det):
        if 'NA' in str(det.param("g")):
            if 'NA' in str(det.param("psat")):
                g = self._noise.G(
                    det.param("psat_fact") * opt_pow, det.param("n"),
                    det.param("tb"), det.param("tc"))
            else:
                g = self._noise.G(
                    det.param("psat"), det.param("n"),
                    det.param("tb"), det.param("tc"))
        else:
            g = det.param("g")
        if 'NA' in str(det.param("flink")):
            return self._noise.bolo_NEP(
                self._noise.Flink(
                    det.param("n"), det.param("tb"), det.param("tc")),
                g, det.param("tc"))
        else:
            return self._noise.bolo_NEP(
                det.param("flink"), g, det.param("tc"))

    def _read_NEP(self, opt_pow, det):
        if 'NA' in str(det.param("nei")):
            return 'NA'
        elif 'NA' in str(det.param("bolo_r")):
            return 'NA'
        elif 'NA' in str(det.param("psat")):
            p_bias = (det.param("psat_fact") - 1.) * opt_pow
            return self._noise.read_NEP(
                p_bias, det.param("bolo_r"), det.param("nei"))
        else:
            if opt_pow >= det.param("psat"):
                return 0.
            else:
                p_bias = det.param("psat") - opt_pow
                return self._noise.read_NEP(
                    p_bias, det.param("bolo_r"), det.param("nei"))

    def _Trj_over_Tcmb(self, freqs):
        factor_spec = self._phys.Trj_over_Tb(freqs, self._phys.Tcmb)
        bw = freqs[-1] - freqs[0]
        factor = np.trapz(factor_spec, freqs)/bw
        return factor

    def _buffer_tran(self, tran, freqs):
        tran = np.insert(tran, len(tran), [1. for f in freqs], axis=0)
        return np.array(tran).astype(np.float)

    def _opt_table(self):
        shape = np.shape(self._pow_sky_side)
        new_shape = (shape[0] * shape[1], shape[2])
        pow_sky_side = np.transpose(np.reshape(self._pow_sky_side, new_shape))
        pow_det_side = np.transpose(np.reshape(self._pow_det_side, new_shape))
        eff_det_side = np.transpose(np.reshape(self._eff_det_side, new_shape))
        return [pow_sky_side,
                pow_det_side,
                eff_det_side]

    def _num_sky_elem(self, ch):
        if ch.cam.tel.param("site").upper() == "SPACE":
            if ch.cam.tel.exp.sim.param("infg"):
                nelem = 3
            else:
                nelem = 1
        else:
            if ch.cam.tel.exp.sim.param("infg"):
                nelem = 4
            else:
                nelem = 2
        return nelem
