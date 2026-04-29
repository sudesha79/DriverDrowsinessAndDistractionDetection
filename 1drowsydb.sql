-- phpMyAdmin SQL Dump
-- version 2.11.6
-- http://www.phpmyadmin.net
--
-- Host: localhost
-- Generation Time: Apr 22, 2025 at 05:22 AM
-- Server version: 5.0.51
-- PHP Version: 5.2.6

SET SQL_MODE="NO_AUTO_VALUE_ON_ZERO";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;

--
-- Database: `1drowsydb`
--

-- --------------------------------------------------------

--
-- Table structure for table `checktb`
--

CREATE TABLE `checktb` (
  `id` bigint(50) NOT NULL auto_increment,
  `UserName` varchar(250) NOT NULL,
  PRIMARY KEY  (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=latin1 AUTO_INCREMENT=2 ;

--
-- Dumping data for table `checktb`
--

INSERT INTO `checktb` (`id`, `UserName`) VALUES
(1, 'pandi');

-- --------------------------------------------------------

--
-- Table structure for table `ownertb`
--

CREATE TABLE `ownertb` (
  `id` bigint(250) NOT NULL auto_increment,
  `OwnerName` varchar(250) NOT NULL,
  `CompanyName` varchar(250) NOT NULL,
  `Mobile` varchar(250) NOT NULL,
  `Email` varchar(250) NOT NULL,
  `Address` varchar(250) NOT NULL,
  PRIMARY KEY  (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=latin1 AUTO_INCREMENT=6 ;

--
-- Dumping data for table `ownertb`
--

INSERT INTO `ownertb` (`id`, `OwnerName`, `CompanyName`, `Mobile`, `Email`, `Address`) VALUES
(1, 'mani', 'maniTRA', '8148079671', 'm45589207@gmail.com', 'no'),
(2, 'kishore', 'kishoreTRA', '9789463601', 'sangeeth5535@gmail.com', 'No 16, Samnath Plaza, Madurai Main Road, Melapudhur'),
(3, 'sanjay', 'sanjayTRAVALES', '9150630118', 'sanjaybm90@gmail.com', 'no'),
(4, 'saiarun', 'saiarunTRA', '6380103249', 'saiarun0118@gmail.com', 'saiarun'),
(5, 'pandi', 'pandi', '8610968120', 'pandiya2307@gmail.com', 'No 16, Samnath Plaza, Madurai Main Road, Melapudhur');

-- --------------------------------------------------------

--
-- Table structure for table `regtb`
--

CREATE TABLE `regtb` (
  `id` bigint(20) NOT NULL auto_increment,
  `CompanyName` varchar(250) NOT NULL,
  `Mobile` varchar(250) NOT NULL,
  `EmailId` varchar(250) NOT NULL,
  `Address` varchar(250) NOT NULL,
  `Licence` varchar(250) NOT NULL,
  `Aadhar` varchar(250) NOT NULL,
  `Experience` varchar(250) NOT NULL,
  `UserName` varchar(250) NOT NULL,
  `Password` varchar(250) NOT NULL,
  PRIMARY KEY  (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=latin1 AUTO_INCREMENT=6 ;

--
-- Dumping data for table `regtb`
--

INSERT INTO `regtb` (`id`, `CompanyName`, `Mobile`, `EmailId`, `Address`, `Licence`, `Aadhar`, `Experience`, `UserName`, `Password`) VALUES
(1, 'maniTRA', '8148079671', 'm45589207@gmail.com', 'no', '12523634745', '2352346457', '5 year', 'sangeeth', 'sangeeth'),
(2, 'kishoreTRA', '9789463601', 'sangeeth5535@gmail.com', 'No 16, Samnath Plaza, Madurai Main Road, Melapudhur', '12523634745', '2352346457', '5 year', 'sangeeth123', 'sangeeth123'),
(3, 'sanjayTRAVALES', '9150630118', 'sanjaybm90@gmail.com', 'no', '12523634745', '2352346457', '5', 'sanjay', 'sanjay'),
(4, 'saiarunTRA', '6380103249', 'saiarun0118@gmail.com', 'saiarun', '12523634745', '2352346457', '5 year', 'saiarun', 'saiarun'),
(5, 'pandi', '8610968120', 'pandiya2307@gmail.com', 'No 16, Samnath Plaza, Madurai Main Road, Melapudhur', '12523634745343', '32653476455678', '5', 'pandi', 'pandi');
