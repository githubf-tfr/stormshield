# stormshield

Outillage Python d'injection **en lot** sur firewall Stormshield SNS, à partir de fichiers
plats : utilisateurs de la base LDAP interne et blacklists (groupes d'objets réseau/URL).

La cible est l'exploitation courante : ce que l'interface web fait un objet à la fois, cet
outil le fait pour quelques milliers de lignes, de façon rejouable.

## État

Repo amorcé, sans code. La spec et le plan de la première injection sont à écrire ; leur
avancement se lit dans [`KANBAN.md`](./KANBAN.md), les conventions dans
[`CLAUDE.md`](./CLAUDE.md).

## Dialogue avec le firewall

Le SDK officiel [`stormshield.sns.sslclient`](https://pypi.org/project/stormshield.sns.sslclient/)
encapsule l'API SSL du boîtier (`nsrpc` sur HTTPS) et ses commandes CLI SNS. Aucun
identifiant n'est stocké dans le repo : ils sont fournis à l'exécution.
