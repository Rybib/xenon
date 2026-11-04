/* Xenon installer slideshow, shown while files are copied. */
import QtQuick 2.15
import calamares.slideshow 1.0

Presentation {
    id: presentation

    function nextSlide() { presentation.goToNextSlide(); }

    Timer {
        id: advanceTimer
        interval: 9000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: nextSlide()
    }

    component XenonSlide: Slide {
        property string heading
        property string body
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#141A33" }
                GradientStop { position: 1.0; color: "#05070F" }
            }
        }
        Column {
            anchors.centerIn: parent
            width: parent.width * 0.75
            spacing: 18
            Text {
                width: parent.width
                text: heading
                color: "#FFFFFF"
                font.pixelSize: 28
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
            Text {
                width: parent.width
                text: body
                color: "#C9CEE6"
                font.pixelSize: 16
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                lineHeight: 1.25
            }
        }
    }

    XenonSlide {
        heading: "Welcome to Xenon"
        body: "A clean, fast desktop with no ads, no tracking and no bloat. Xenon is open source and built on Debian."
    }
    XenonSlide {
        heading: "Your Windows apps, built in"
        body: "Download a Windows program and open its installer, just like on Windows. It appears in your app grid when it's done. No setup, no extra tools."
    }
    XenonSlide {
        heading: "Made for games"
        body: "DirectX games run through Vulkan with DXVK and VKD3D-Proton, with the latest graphics drivers, GameMode and controller support out of the box."
    }
    XenonSlide {
        heading: "Thousands of Linux apps"
        body: "Software gives you Flathub's app catalog, plus firmware updates for your PC. Security updates install themselves quietly."
    }
    XenonSlide {
        heading: "Private by design"
        body: "No telemetry. A firewall is on from the start, and your disk can be fully encrypted. Your computer works for you."
    }

    function onActivate() { presentation.currentSlide = 0; }
    function onLeave() { }
}
