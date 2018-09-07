"""CREATE TABLE IF NOT EXISTS `product_info` (
`asin` varchar(20) NOT NULL,
`last_update_time` timestamp NOT NULL DEFAULT '0000-00-00 00:00:00',
`title` varchar(500) DEFAULT NULL,
`price` float DEFAULT NULL,
`currency_code` varchar(10) DEFAULT NULL,
`review_num` int(10) DEFAULT NULL,
`star` varchar(50) DEFAULT NULL,
`img1` varchar(1000) DEFAULT NULL,
`img2` varchar(1000) DEFAULT NULL,
`img3` varchar(1000) DEFAULT NULL,
`img4` varchar(1000) DEFAULT NULL,
`img5` varchar(1000) DEFAULT NULL,
`img6` varchar(1000) DEFAULT NULL,
`img7` varchar(1000) DEFAULT NULL,
`img8` varchar(1000) DEFAULT NULL,
`img9` varchar(1000) DEFAULT NULL,
`img0` varchar(1000) DEFAULT NULL,
`rank1` varchar(500) DEFAULT NULL,
`rank2` varchar(500) DEFAULT NULL,
`rank3` varchar(500) DEFAULT NULL,
`rank4` varchar(500) DEFAULT NULL,
`rank0` varchar(500) DEFAULT NULL,
PRIMARY KEY (`asin`,`last_update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;"""

+------------------+---------------+------+-----+---------------------+-------+
| Field            | Type          | Null | Key | Default             | Extra |
+------------------+---------------+------+-----+---------------------+-------+
| asin             | varchar(20)   | NO   | PRI | NULL                |       |
| last_update_time | timestamp     | NO   | PRI | 0000-00-00 00:00:00 |       |
| title            | varchar(500)  | YES  |     | NULL                |       |
| price            | float         | YES  |     | NULL                |       |
| currency_code    | varchar(10)   | YES  |     | NULL                |       |
| review_num       | int(10)       | YES  |     | NULL                |       |
| star             | varchar(50)   | YES  |     | NULL                |       |
| img1             | varchar(1000) | YES  |     | NULL                |       |
| img2             | varchar(1000) | YES  |     | NULL                |       |
| img3             | varchar(1000) | YES  |     | NULL                |       |
| img4             | varchar(1000) | YES  |     | NULL                |       |
| img5             | varchar(1000) | YES  |     | NULL                |       |
| img6             | varchar(1000) | YES  |     | NULL                |       |
| img7             | varchar(1000) | YES  |     | NULL                |       |
| img8             | varchar(1000) | YES  |     | NULL                |       |
| img9             | varchar(1000) | YES  |     | NULL                |       |
| img0             | varchar(1000) | YES  |     | NULL                |       |
| rank1            | varchar(500)  | YES  |     | NULL                |       |
| rank2            | varchar(500)  | YES  |     | NULL                |       |
| rank3            | varchar(500)  | YES  |     | NULL                |       |
| rank4            | varchar(500)  | YES  |     | NULL                |       |
| rank0            | varchar(500)  | YES  |     | NULL                |       |
+------------------+---------------+------+-----+---------------------+-------+
