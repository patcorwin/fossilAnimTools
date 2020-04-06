# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'G:\Projects\_tools\_maya\fossilAnimTools\fossilAnimTools\spacePresetPrompt_qtui.ui',
# licensing of 'G:\Projects\_tools\_maya\fossilAnimTools\fossilAnimTools\spacePresetPrompt_qtui.ui' applies.
#
# Created: Sun Apr  5 19:32:04 2020
#      by: pyside2-uic  running on PySide2 5.11.1
#
# WARNING! All changes made in this file will be lost!

from PySide2 import QtCore, QtGui, QtWidgets

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(446, 124)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(Dialog)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.location = QtWidgets.QComboBox(Dialog)
        self.location.setObjectName("location")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.location)
        self.label_2 = QtWidgets.QLabel(Dialog)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.nameEntry = QtWidgets.QLineEdit(Dialog)
        self.nameEntry.setObjectName("nameEntry")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.nameEntry)
        self.verticalLayout.addLayout(self.formLayout)
        self.message = QtWidgets.QLabel(Dialog)
        self.message.setText("")
        self.message.setObjectName("message")
        self.verticalLayout.addWidget(self.message)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.ok = QtWidgets.QPushButton(Dialog)
        self.ok.setObjectName("ok")
        self.horizontalLayout.addWidget(self.ok)
        self.cancel = QtWidgets.QPushButton(Dialog)
        self.cancel.setObjectName("cancel")
        self.horizontalLayout.addWidget(self.cancel)
        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QtWidgets.QApplication.translate("Dialog", "Dialog", None, -1))
        self.label.setText(QtWidgets.QApplication.translate("Dialog", "Location", None, -1))
        self.label_2.setText(QtWidgets.QApplication.translate("Dialog", "Name", None, -1))
        self.ok.setText(QtWidgets.QApplication.translate("Dialog", "Ok", None, -1))
        self.cancel.setText(QtWidgets.QApplication.translate("Dialog", "Cancel", None, -1))

