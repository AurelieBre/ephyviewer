# -*- coding: utf-8 -*-
#~ from __future__ import (unicode_literals, print_function, division, absolute_import)

from collections import OrderedDict
import time
import sys
import pickle

from .myqt import QT, QT_MODE
from .navigation import NavigationToolBar

from .traceviewer import TraceViewer
from .epochviewer import EpochViewer
from .eventlist import EventList
from .spiketrainviewer import SpikeTrainViewer

location_to_qt = {
    'left': QT.LeftDockWidgetArea,
    'right': QT.RightDockWidgetArea,
    'top': QT.TopDockWidgetArea,
    'bottom': QT.BottomDockWidgetArea,
}

orientation_to_qt = {
    'horizontal': QT.Horizontal,
    'vertical': QT.Vertical,
}


# ─────────────────────────────────────────────────────────────────────────────
# OverlayWidget
# ─────────────────────────────────────────────────────────────────────────────

class OverlayWidget(QT.QWidget):
    """
    Composites two viewer widgets with true pixel-level alpha blending while
    keeping widget_top fully interactive (including pyqtgraph scenes).

    Architecture
    ------------
    The fundamental conflict is:
      - For transparency we need to control painting (QPainter compositing).
      - For interactivity we need Qt's native event dispatch, which only works
        for real child widgets — NOT for hidden top-level windows receiving
        forwarded events. pyqtgraph's GraphicsView in particular swallows
        mouse events entirely inside its QGraphicsScene; sendEvent on the
        top-level window never reaches scene items like RectItem or
        LinearRegionItem.

    Solution
    --------
    widget_bottom  →  hidden top-level window (WA_DontShowOnScreen).
                      Rendered offscreen, grabbed as QPixmap, painted into
                      the background of OverlayWidget at `opacity`.

    widget_top     →  real visible child widget of OverlayWidget, filling
                      the whole area. Given WA_TranslucentBackground so its
                      own background is transparent — only its content
                      (traces, epoch bars, controls) is painted.
                      Qt dispatches all mouse/keyboard events to it natively,
                      so pyqtgraph scenes, QTableWidget, QToolBar etc. all
                      work exactly as if the widget stood alone.
                      A QGraphicsOpacityEffect fades its content to `opacity`
                      so the two layers blend visually.

    Result: bottom layer painted at `opacity`, top layer at `opacity` via
    effect → genuine visual blending, full native interactivity.

    Parameters
    ----------
    widget_bottom : QWidget   – viewer painted in the background
    widget_top    : QWidget   – viewer on top, fully interactive
    opacity       : float     – opacity per layer (default 0.5 = 50 %)
    """

    def __init__(self, widget_bottom, widget_top, opacity=0.5, parent=None):
        super().__init__(parent)
        self.widget_bottom = widget_bottom
        self.widget_top    = widget_top
        self._opacity      = opacity

        # ── widget_bottom: hidden offscreen, grabbed in paintEvent ────────
        widget_bottom.setParent(None)
        widget_bottom.setWindowFlags(
            QT.Qt.Tool |
            QT.Qt.FramelessWindowHint
        )
        widget_bottom.setAttribute(QT.Qt.WA_DontShowOnScreen, True)
        widget_bottom.show()   # must be shown so Qt fills its pixel buffer

        # ── widget_top: real child, transparent background, opacity effect ─
        widget_top.setParent(self)
        widget_top.setAttribute(QT.Qt.WA_TranslucentBackground, True)

        self._opacity_effect = QT.QGraphicsOpacityEffect(widget_top)
        self._opacity_effect.setOpacity(opacity)
        widget_top.setGraphicsEffect(self._opacity_effect)

        widget_top.show()

        self._sync_sizes()

        # Refresh the background (bottom layer) ~60 fps
        self._timer = QT.QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    # ── sizing ────────────────────────────────────────────────────────────────
    def _sync_sizes(self):
        sz = self.size()
        if not sz.isValid() or sz.isEmpty():
            sz = QT.QSize(800, 600)
        self.widget_bottom.resize(sz)
        self.widget_top.setGeometry(0, 0, sz.width(), sz.height())

    def resizeEvent(self, event):
        sz = event.size()
        self.widget_bottom.resize(sz)
        self.widget_top.setGeometry(0, 0, sz.width(), sz.height())
        super().resizeEvent(event)

    # ── painting: only the bottom layer needs manual compositing ─────────────
    def paintEvent(self, event):
        """
        Paint widget_bottom (offscreen grab) at `opacity` first.
        widget_top is a real child so Qt paints it automatically on top
        via its own QGraphicsOpacityEffect — no manual step needed.
        """
        painter = QT.QPainter(self)
        painter.setRenderHint(QT.QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self.widget_bottom.grab())
        painter.end()

    # ── cleanup ───────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._timer.stop()
        self.widget_bottom.close()
        # widget_top is a real child, Qt will close it automatically
        super().closeEvent(event)

    # ── public API ────────────────────────────────────────────────────────────
    def set_opacity(self, opacity):
        """Change blending opacity of both layers at runtime (0.0 – 1.0)."""
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self._opacity_effect.setOpacity(self._opacity)
        self.update()


# ─────────────────────────────────────────────────────────────────────────────
# MainViewer
# ─────────────────────────────────────────────────────────────────────────────

class MainViewer(QT.QMainWindow):
    def __init__(self, debug=False, settings_name=None, parent=None,
                 global_xsize_zoom=False, **navigation_params):
        QT.QMainWindow.__init__(self, parent)

        self.debug = debug
        if self.debug:
            print('debug True')
            print('QT_MODE', QT_MODE)

        self.settings_name = settings_name
        if self.settings_name is not None:
            pyver = '.'.join(str(e) for e in sys.version_info[0:3])
            appname = 'ephyviewer' + '_py' + pyver
            self.settings = QT.QSettings(appname, self.settings_name)

        self.global_xsize_zoom = global_xsize_zoom
        self.setDockNestingEnabled(True)

        self.viewers = OrderedDict()

        self.navigation_toolbar = NavigationToolBar(**navigation_params)

        dock = self.navigation_dock = QT.QDockWidget('navigation', self)
        dock.setObjectName('navigation')
        dock.setWidget(self.navigation_toolbar)
        dock.setTitleBarWidget(QT.QWidget())
        dock.setFeatures(QT.DockWidget.NoDockWidgetFeatures)
        self.addDockWidget(QT.TopDockWidgetArea, dock)

        self.navigation_toolbar.time_changed.connect(self.on_time_changed)
        self.navigation_toolbar.xsize_changed.connect(self.on_xsize_changed)
        self.navigation_toolbar.auto_scale_requested.connect(self.auto_scale)

        self.load_one_setting('navigation_toolbar', self.navigation_toolbar)

    # ──────────────────────────────────────────────────────────────────────────
    def add_view(self, widget, location='bottom', orientation='vertical',
                 tabify_with=None, split_with=None,
                 overlay_with=None, overlay_opacity=0.5):
        """
        Add a viewer to the main window.

        New parameters
        --------------
        overlay_with : str or None
            Name of an already-added viewer. The new viewer will be blended
            on top of it. The new viewer remains fully interactive (clicks,
            drags, pyqtgraph scenes, table widgets all work normally).
        overlay_opacity : float
            Opacity (0–1) applied to each layer. Default 0.5 = 50 %.
        """
        name = widget.name
        assert name not in self.viewers, 'Viewer already in MainViewer'

        # ── OVERLAY ───────────────────────────────────────────────────────────
        if overlay_with is not None:
            assert overlay_with in self.viewers, \
                '"{}" does not exist – add it first'.format(overlay_with)

            other      = self.viewers[overlay_with]
            other_dock = other['dock']

            overlay = OverlayWidget(
                widget_bottom=other['widget'],
                widget_top=widget,
                opacity=overlay_opacity,
            )
            other_dock.setWidget(overlay)
            other_dock.setWindowTitle('{} + {}'.format(overlay_with, name))

            self.viewers[name] = {'widget': widget, 'dock': other_dock,
                                  'overlay': overlay}
            other['overlay'] = overlay

        # ── TABIFY ────────────────────────────────────────────────────────────
        elif tabify_with is not None:
            assert tabify_with in self.viewers, \
                '"{}" does not exist'.format(tabify_with)
            dock = QT.QDockWidget(name)
            dock.setObjectName(name)
            dock.setWidget(widget)
            self.tabifyDockWidget(self.viewers[tabify_with]['dock'], dock)
            self.viewers[name] = {'widget': widget, 'dock': dock}

        # ── SPLIT ─────────────────────────────────────────────────────────────
        elif split_with is not None:
            assert split_with in self.viewers, \
                '"{}" does not exist'.format(split_with)
            dock = QT.QDockWidget(name)
            dock.setObjectName(name)
            dock.setWidget(widget)
            self.splitDockWidget(
                self.viewers[split_with]['dock'], dock,
                orientation_to_qt[orientation])
            self.viewers[name] = {'widget': widget, 'dock': dock}

        # ── DEFAULT ───────────────────────────────────────────────────────────
        else:
            dock = QT.QDockWidget(name)
            dock.setObjectName(name)
            dock.setWidget(widget)
            self.addDockWidget(location_to_qt[location], dock,
                               orientation_to_qt[orientation])
            self.viewers[name] = {'widget': widget, 'dock': dock}

        # ── common wiring (unchanged from original) ───────────────────────────
        self.load_one_setting(name, widget)

        widget.time_changed.connect(self.on_time_changed)
        if self.global_xsize_zoom and hasattr(widget, 'params_controller'):
            widget.params_controller.xsize_zoomed.connect(self.set_xsize)

        if hasattr(widget.source, 't_start'):
            if len(self.viewers) == 1:
                t_start = widget.source.t_start
                t_stop  = widget.source.t_stop
            else:
                t_start = min(self.navigation_toolbar.t_start,
                              widget.source.t_start)
                t_stop  = max(self.navigation_toolbar.t_stop,
                              widget.source.t_stop)
            self.navigation_toolbar.set_start_stop(t_start, t_stop, seek=True)

    # ──────────────────────────────────────────────────────────────────────────
    def set_overlay_opacity(self, name, opacity):
        """
        Adjust blending opacity of an overlay pair at runtime.

        Parameters
        ----------
        name    : str   – name of either viewer in the pair
        opacity : float – new opacity (0.0 – 1.0)
        """
        entry = self.viewers.get(name)
        if entry is None:
            raise KeyError('Viewer "{}" not found'.format(name))
        overlay = entry.get('overlay')
        if overlay is None:
            raise ValueError('Viewer "{}" is not part of an overlay'.format(name))
        overlay.set_opacity(opacity)

    # ──────────────────────────────────────────────────────────────────────────
    def load_one_setting(self, name, widget):
        if self.settings_name is not None:
            value = self.settings.value('viewer_' + name)
            if value is not None:
                try:
                    if QT_MODE == 'PyQt4' and sys.version_info[0] == 2:
                        if type(value) == QT.QVariant:
                            value = bytes(value.toPyObject())
                    value = pickle.loads(value)
                    widget.set_settings(value)
                except Exception:
                    print('erreur load settings', name)

    def save_all_settings(self):
        if self.debug:
            print('save_all_settings')
        if self.settings_name is not None:
            for name, d in self.viewers.items():
                value = d['widget'].get_settings()
                if value is not None:
                    self.settings.setValue('viewer_' + name,
                                           pickle.dumps(value))
            value = self.navigation_toolbar.get_settings()
            if value is not None:
                self.settings.setValue('viewer_navigation_toolbar',
                                       pickle.dumps(value))

    def on_time_changed(self, t):
        for name, viewer in self.viewers.items():
            if viewer['widget'] != self.sender():
                t0 = time.time()
                viewer['widget'].seek(t)
                if self.debug:
                    t1 = time.time()
                    print('refresh duration for', name, t1 - t0, 's')
        if self.navigation_toolbar != self.sender():
            self.navigation_toolbar.seek(t, emit=False)

    def on_xsize_changed(self, xsize):
        for name, viewer in self.viewers.items():
            if hasattr(viewer['widget'], 'set_xsize'):
                viewer['widget'].set_xsize(xsize)

    def auto_scale(self):
        for name, viewer in self.viewers.items():
            if hasattr(viewer['widget'], 'auto_scale'):
                viewer['widget'].auto_scale()

    def seek(self, t):
        for name, viewer in self.viewers.items():
            viewer['widget'].seek(t)
        self.navigation_toolbar.seek(t, emit=False)

    def set_xsize(self, xsize):
        if hasattr(self.navigation_toolbar, 'spinbox_xsize'):
            self.navigation_toolbar.spinbox_xsize.setValue(xsize)

    def closeEvent(self, event):
        for name, viewer in self.viewers.items():
            viewer['widget'].close()
        self.save_all_settings()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# compose_mainviewer_from_sources  (unchanged from original)
# ─────────────────────────────────────────────────────────────────────────────

def compose_mainviewer_from_sources(sources, mainviewer=None):
    """
    Helper that composes a window from several sources with basic rules.

    Use internally in:
      * standalone
      * when generating mainviewer from neo segment
    """
    if mainviewer is None:
        mainviewer = MainViewer(show_auto_scale=True)

    for i, sig_source in enumerate(sources['signal']):
        view = TraceViewer(source=sig_source, name='signal {}'.format(i))
        view.params['scale_mode'] = 'same_for_all'
        view.params['display_labels'] = True
        if i == 0:
            mainviewer.add_view(view)
        else:
            mainviewer.add_view(view, tabify_with='signal {}'.format(i - 1))
        view.auto_scale()

    for i, spike_source in enumerate(sources['spike']):
        view = SpikeTrainViewer(source=spike_source, name='spikes')
        mainviewer.add_view(view)

    for i, ep_source in enumerate(sources['epoch']):
        view = EpochViewer(source=ep_source, name='epochs')
        mainviewer.add_view(view)

    if 'event' in sources and len(sources['event']) > 0:
        ev_source_list = sources['event']
    else:
        ev_source_list = sources['epoch']
    for i, ev_source in enumerate(ev_source_list):
        view = EventList(source=ev_source, name='Event list')
        mainviewer.add_view(view, location='bottom', orientation='horizontal')

    return mainviewer
