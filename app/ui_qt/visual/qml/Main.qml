// Variant B of the visual-ceiling spike: the main screen in Qt Quick.
// Context properties from qml_main.py: backend, consoleModel, theme (colors),
// labels (translated in Python), isDark, micaOn.
import QtQuick
import QtQuick.Window
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Shapes

Window {
    id: win
    width: 1180; height: 760
    visible: false
    title: "ZeroBlockBridge"
    color: micaOn ? "transparent" : theme.bg

    readonly property string fontText: "Segoe UI Variable Text"
    readonly property string fontDisplay: "Segoe UI Variable Display"
    readonly property string fontMono: "Cascadia Mono"
    function a(c, alpha) { return Qt.rgba(c.r, c.g, c.b, alpha) }
    function icon(name, c) { return "image://icons/" + name + "/" + c.toString().substring(1) }

    // -- background: soft aurora blobs the glass panels blur -----------------
    Item {
        id: aurora
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: win.a(theme.bg, micaOn ? 0.70 : 1) }
        Blob { id: blobA; size: 900; x: win.width * 0.45; y: -420; tint: win.a(theme.primary, isDark ? 0.22 : 0.16)
            SequentialAnimation on x {
                loops: Animation.Infinite
                NumberAnimation { to: win.width * 0.25; duration: 9000; easing.type: Easing.InOutSine }
                NumberAnimation { to: win.width * 0.45; duration: 9000; easing.type: Easing.InOutSine }
            }
        }
        Blob { size: 760; x: -360; y: win.height - 420; tint: win.a(theme.starting, isDark ? 0.10 : 0.09) }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // -- sidebar: frosted glass over the aurora --------------------------
        Item {
            Layout.preferredWidth: 250
            Layout.fillHeight: true
            ShaderEffectSource {
                id: behindSide
                anchors.fill: parent
                sourceItem: aurora
                sourceRect: Qt.rect(0, 0, width, height)
                visible: false
            }
            MultiEffect {
                anchors.fill: parent
                source: behindSide
                blurEnabled: true; blur: 1.0; blurMax: 48
                saturation: 0.2
            }
            Rectangle {
                anchors.fill: parent
                color: win.a(theme.sidebar, micaOn ? 0.45 : 0.78)
                Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: win.a(theme.border, 0.6) }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10
                RowLayout {
                    spacing: 8
                    Image { source: win.icon("layers", theme.primary); sourceSize: Qt.size(22, 22) }
                    Text { text: "ZeroBlockBridge"; color: theme.text; font.family: win.fontDisplay; font.pixelSize: 16; font.weight: Font.Bold }
                }
                Text {
                    Layout.topMargin: 8
                    text: labels.servers.toUpperCase(); color: theme.muted
                    font.family: win.fontText; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 0.6
                }
                ListView {
                    id: serverList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 2
                    focus: true
                    activeFocusOnTab: true
                    keyNavigationEnabled: true
                    Accessible.role: Accessible.List
                    Accessible.name: labels.servers
                    model: ListModel { id: serverModel }
                    highlightMoveDuration: 240
                    highlightMoveVelocity: -1
                    highlight: Rectangle {
                        radius: 9
                        color: win.a(theme.primary, 0.22)
                        Rectangle { x: 0; y: 9; width: 3; height: parent.height - 18; radius: 1.5; color: theme.primary }
                    }
                    delegate: Item {
                        required property string name
                        required property int index
                        width: serverList.width; height: 40
                        Accessible.role: Accessible.ListItem
                        Accessible.name: name
                        Rectangle {
                            anchors.fill: parent; radius: 9
                            color: hover.hovered && !parent.ListView.isCurrentItem ? win.a(theme.ghost_hover, 0.6) : "transparent"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 14; spacing: 10
                            Image { source: win.icon("package", theme.muted); sourceSize: Qt.size(18, 18) }
                            Text {
                                Layout.fillWidth: true; text: name; elide: Text.ElideRight; color: theme.text
                                font.family: win.fontText; font.pixelSize: 13
                                font.weight: parent.parent.ListView.isCurrentItem ? Font.DemiBold : Font.Normal
                            }
                        }
                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: { serverList.currentIndex = index; backend.select(name) } }
                    }
                    onCurrentIndexChanged: if (currentIndex >= 0 && activeFocus) backend.select(serverModel.get(currentIndex).name)
                    add: Transition {
                        ParallelAnimation {
                            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 260 }
                            NumberAnimation { property: "x"; from: -24; to: 0; duration: 260; easing.type: Easing.OutCubic }
                        }
                    }
                    remove: Transition {
                        ParallelAnimation {
                            NumberAnimation { property: "opacity"; to: 0; duration: 200 }
                            NumberAnimation { property: "x"; to: 24; duration: 200 }
                        }
                    }
                    displaced: Transition { NumberAnimation { properties: "y"; duration: 220; easing.type: Easing.OutCubic } }
                }
                ZButton { Layout.fillWidth: true; label: labels.newServer; iconName: "plus"; role: "primary" }
            }
        }

        // -- main column -----------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 20
            spacing: 16

            Card {
                Layout.fillWidth: true
                Layout.preferredHeight: 96
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 22; anchors.rightMargin: 18
                    spacing: 10
                    Item {
                        id: titleBlock
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        property string shownName: backend.selected || labels.selectServer
                        Column {
                            id: titleCol
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            Text { text: titleBlock.shownName; color: theme.text; font.family: win.fontDisplay; font.pixelSize: 22; font.weight: Font.Bold }
                            Item {
                                width: 200; height: 16
                                Text { visible: !backend.loading; text: backend.engineText; color: theme.muted; font.family: win.fontText; font.pixelSize: 12 }
                                Skeleton { visible: backend.loading; width: 120; height: 12; anchors.verticalCenter: parent.verticalCenter }
                            }
                        }
                        // Page transition on server switch: out, swap, in.
                        SequentialAnimation {
                            id: switchAnim
                            ParallelAnimation {
                                NumberAnimation { target: titleCol; property: "opacity"; to: 0; duration: 90 }
                                NumberAnimation { target: titleCol; property: "anchors.verticalCenterOffset"; to: -8; duration: 90 }
                            }
                            ScriptAction { script: titleBlock.shownName = backend.selected || labels.selectServer }
                            PropertyAction { target: titleCol; property: "anchors.verticalCenterOffset"; value: 10 }
                            ParallelAnimation {
                                NumberAnimation { target: titleCol; property: "opacity"; to: 1; duration: 240; easing.type: Easing.OutCubic }
                                NumberAnimation { target: titleCol; property: "anchors.verticalCenterOffset"; to: 0; duration: 240; easing.type: Easing.OutCubic }
                            }
                        }
                        Connections { target: backend; function onSelectedChanged() { switchAnim.restart() } }
                    }
                    StatusPill { phase: backend.phase; label: backend.statusText }
                    Chip { label: backend.ramText; visible: label !== "" }
                    Chip { label: backend.playersText; visible: label !== "" }
                    ZButton {
                        Layout.preferredWidth: 124
                        label: backend.startLabel
                        iconName: backend.phase === "offline" ? "play" : "stop"
                        role: backend.phase === "offline" ? "primary" : "danger"
                        enabled: backend.canStart
                        onClicked: backend.startStop()
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14; spacing: 8
                    RowLayout {
                        spacing: 8
                        Image { source: win.icon("terminal", theme.muted); sourceSize: Qt.size(16, 16) }
                        Text { text: labels.console.toUpperCase(); color: theme.muted; font.family: win.fontText; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 0.6 }
                    }
                    ListView {
                        id: consoleView
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true
                        visible: !backend.loading
                        model: consoleModel
                        reuseItems: true
                        Accessible.role: Accessible.StaticText
                        Accessible.name: labels.console
                        property bool follow: true
                        onMovementEnded: follow = atYEnd
                        onCountChanged: if (follow) positionViewAtEnd()
                        delegate: Text {
                            required property string line
                            width: consoleView.width; text: line; wrapMode: Text.WrapAnywhere
                            color: theme.text; font.family: win.fontMono; font.pixelSize: 12
                        }
                    }
                    Column {
                        visible: backend.loading; spacing: 10
                        Repeater { model: [420, 360, 480, 300]; Skeleton { width: modelData; height: 10 } }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Rectangle {
                    Layout.fillWidth: true; height: 40; radius: 10
                    color: win.a(theme.card, micaOn ? 0.92 : 1)
                    border.width: cmd.activeFocus ? 2 : 1
                    border.color: cmd.activeFocus ? theme.primary : theme.border
                    Behavior on border.color { ColorAnimation { duration: 140 } }
                    opacity: cmd.enabled ? 1 : 0.6
                    Image { id: cmdIcon; x: 12; anchors.verticalCenter: parent.verticalCenter; source: win.icon("terminal", theme.muted); sourceSize: Qt.size(16, 16) }
                    TextInput {
                        id: cmd
                        anchors { left: cmdIcon.right; leftMargin: 10; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                        enabled: backend.phase !== "offline"
                        color: theme.text; font.family: win.fontText; font.pixelSize: 13; clip: true
                        selectionColor: theme.primary
                        activeFocusOnTab: true
                        Accessible.role: Accessible.EditableText
                        Accessible.name: labels.command
                        onAccepted: if (backend.sendCommand(text)) text = ""
                        Text { visible: !cmd.text; text: labels.commandHint; color: theme.muted; font: cmd.font }
                    }
                }
                ZButton { label: labels.send; iconName: "arrow"; role: "ghost"; enabled: cmd.enabled; onClicked: if (backend.sendCommand(cmd.text)) cmd.text = "" }
            }
        }
    }

    // -- keep the sidebar model in step with backend.servers (diff, so the
    //    add/remove transitions run) -----------------------------------------
    function syncServers() {
        var want = backend.servers
        for (var i = serverModel.count - 1; i >= 0; --i)
            if (want.indexOf(serverModel.get(i).name) < 0) serverModel.remove(i)
        for (var j = 0; j < want.length; ++j) {
            if (j >= serverModel.count || serverModel.get(j).name !== want[j]) serverModel.insert(j, { name: want[j] })
        }
        syncSelection()
    }
    function syncSelection() {
        for (var i = 0; i < serverModel.count; ++i)
            if (serverModel.get(i).name === backend.selected) { serverList.currentIndex = i; return }
    }
    Connections {
        target: backend
        function onServersChanged() { win.syncServers() }
        function onSelectedChanged() { win.syncSelection() }
    }

    // -- components ------------------------------------------------------------
    // Soft light spot: a radial gradient to transparent (no blur pass needed).
    component Blob: Shape {
        property real size: 600
        property color tint
        width: size; height: size
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: -1
            fillGradient: RadialGradient {
                centerX: size / 2; centerY: size / 2; centerRadius: size / 2
                focalX: size / 2; focalY: size / 2
                GradientStop { position: 0; color: tint }
                GradientStop { position: 1; color: "transparent" }
            }
            PathRectangle { x: 0; y: 0; width: size; height: size }
        }
    }

    component Card: Item {
        default property alias content: body.data
        Rectangle {
            id: plate
            anchors.fill: parent; radius: 14
            color: win.a(theme.card, micaOn ? 0.90 : 1)
            border.color: win.a(theme.border, 0.7); border.width: 1
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true; shadowBlur: 0.9; shadowVerticalOffset: 6
                shadowColor: Qt.rgba(0, 0, 0, isDark ? 0.45 : 0.16)
            }
        }
        Item { id: body; anchors.fill: parent }
    }

    component Chip: Rectangle {
        property string label
        implicitWidth: chipText.implicitWidth + 26; implicitHeight: 26; radius: 13
        color: theme.badge_bg
        Accessible.role: Accessible.StaticText
        Accessible.name: label
        Text { id: chipText; anchors.centerIn: parent; text: parent.label; color: theme.badge_text; font.family: win.fontDisplay; font.pixelSize: 12; font.weight: Font.DemiBold }
    }

    component StatusPill: Rectangle {
        id: pill
        property string phase: "offline"
        property string label
        property color tone: phase === "running" ? theme.online : phase === "starting" ? theme.starting : theme.offline
        implicitWidth: pillText.implicitWidth + 44; implicitHeight: 30; radius: 15
        color: win.a(tone, 0.16)
        Behavior on tone { ColorAnimation { duration: 300 } }
        Accessible.role: Accessible.StaticText
        Accessible.name: label
        Item {
            x: 13; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8
            Rectangle {
                id: ring; anchors.centerIn: parent; width: 8; height: 8; radius: width / 2
                color: pill.tone; opacity: 0
                SequentialAnimation on scale {
                    running: pill.phase !== "offline"; loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 2.8; duration: 1600; easing.type: Easing.OutCubic }
                }
                SequentialAnimation on opacity {
                    running: pill.phase !== "offline"; loops: Animation.Infinite
                    NumberAnimation { from: 0.5; to: 0; duration: 1600; easing.type: Easing.OutCubic }
                }
            }
            Rectangle {
                anchors.fill: parent; radius: 4; color: pill.tone
                layer.enabled: pill.phase !== "offline"
                layer.effect: MultiEffect { shadowEnabled: true; shadowColor: pill.tone; shadowBlur: 0.6; shadowHorizontalOffset: 0; shadowVerticalOffset: 0 }
            }
        }
        Text {
            id: pillText; x: 30; anchors.verticalCenter: parent.verticalCenter
            text: pill.label; color: pill.phase === "offline" ? theme.muted : pill.tone
            font.family: win.fontDisplay; font.pixelSize: 13; font.weight: Font.DemiBold
        }
    }

    component Skeleton: Rectangle {
        id: sk
        radius: height / 2
        color: theme.ghost_hover
        clip: true
        Rectangle {
            width: sk.width * 0.6; height: sk.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.5; color: win.a(isDark ? "white" : "black", isDark ? 0.10 : 0.06) }
                GradientStop { position: 1; color: "transparent" }
            }
            NumberAnimation on x { from: -sk.width * 0.6; to: sk.width; duration: 1100; loops: Animation.Infinite; running: sk.visible }
        }
    }

    component ZButton: Rectangle {
        id: btn
        property string label
        property string iconName
        property string role: "ghost"
        signal clicked()
        readonly property color base: role === "primary" ? theme.primary : role === "danger" ? theme.danger : theme.ghost
        readonly property color hover: role === "primary" ? theme.primary_hover : role === "danger" ? theme.danger_hover : theme.ghost_hover
        readonly property color fg: !enabled ? theme.muted : role === "ghost" ? theme.text : theme.on_accent
        implicitWidth: row.implicitWidth + 32; implicitHeight: 38; radius: 9
        color: !enabled ? theme.ghost : mouse.pressed ? Qt.darker(hover, 1.1) : mouse.containsMouse ? hover : base
        Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }
        border.width: role === "ghost" || activeFocus ? (activeFocus ? 2 : 1) : 0
        border.color: activeFocus ? theme.primary : theme.border
        scale: mouse.pressed ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: label
        Accessible.onPressAction: if (enabled) clicked()
        Keys.onSpacePressed: if (enabled) clicked()
        Keys.onReturnPressed: if (enabled) clicked()
        RowLayout {
            id: row; anchors.centerIn: parent; spacing: 8
            Image { visible: btn.iconName !== ""; source: btn.iconName ? win.icon(btn.iconName, btn.fg) : ""; sourceSize: Qt.size(16, 16) }
            Text { text: btn.label; color: btn.fg; font.family: win.fontDisplay; font.pixelSize: 13; font.weight: Font.DemiBold }
        }
        MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: if (btn.enabled) btn.clicked() }
    }
}
