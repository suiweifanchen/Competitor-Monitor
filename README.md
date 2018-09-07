# Competitor-Monitor
Monitor your competitors' product listings

This is a multi-thread crawler of Amz, with ip proxy, while you need to maintain a ip proxy pool first.

* It can help you monitor your competitors' listing, including the info of titles, price, reviews, stars, etc.
* After searching and handlering all the products, the program will send a mail to you which is about the differece between the info of the newest and the last.
* It can also remove the invalid ASIN automatically, from `asin.txt` to `asin_invalid.txt`.

You only need to provide the ASIN of the products, that you want to monitor, to the program. You can add you ASINs into the `asin.txt`.
